"""Scientific figures and a concise source/coverage report; no publication."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from analysis.product_metrics import product_scores


def interpretation(root, daily):
    """Report product support and paired attribution without selecting a method."""
    out = root / 'results'
    primary = daily[(daily.reason == 'usable') & (daily['product'] == 'native')]
    pay = primary[primary.site == 'PAY']
    phase = pay.observed_phase_high - pay.observed_phase_low
    rolling = []
    for day, group in pay.groupby('day'):
        valid = group[np.isfinite(group.rolling_observed_uvi + group.rolling_predicted_uvi)]
        rolling.append(dict(day=int(day), **product_scores(valid.rolling_observed_uvi, valid.rolling_predicted_uvi)))
    support = dict(
        primary_site_days=len(primary),
        payerne_phase_range_max=float(phase.max()),
        payerne_phase_range_p95=float(phase.quantile(.95)),
        payerne_phase_display_ambiguous=int((np.floor(pay.observed_phase_low + .5) != np.floor(pay.observed_phase_high + .5)).sum()),
        model_rolling_minus_halfhour_max=float((primary.rolling_predicted_uvi-primary.predicted_uvi).max()),
        payerne_rolling_scores=rolling,
    )
    (out / 'product_support.json').write_text(json.dumps(support, indent=2))
    lines = ['## Product implications and next steps', '',
        f'The primary assessment contains {len(primary)} complete site-days across three locations. This supports continued internal map-product development. It does not yet qualify every Swiss region, Alpine elevation band, season or extreme category.', '',
        'Payerne provides the strongest lowland evidence in this assessment, but has no accepted spring measurements. Weissfluhjoch remains the weakest site and has only five available two-day windows in 2026. The two unscored SACRaM locations leave major high-Alpine and southern-Swiss gaps.', '',
        '### Paired shortwave attribution', '',
        'Positive values below mean that replacing forecast shortwave with measured shortwave reduces daily MAE. Each comparison uses exactly the same dates; these are diagnostic substitutions, not deployable forecasts.', '',
        '| Site | Forecast day | Paired days | MAE reduction (UVI) | Date-block 95% interval |',
        '|---|---:|---:|---:|---:|']
    for r in json.loads((out / 'paired_comparisons.json').read_text()):
        if r['right'] == 'measured_sw':
            lo, hi = r['ci95']
            lines.append(f"| {r['site']} | {r['day']+1} | {r['dates']} | {r['delta_mae']:.3f} | {lo:.3f}–{hi:.3f} |")
    lines += ['', 'The paired results make cloud/shortwave inputs a useful improvement priority. Remaining errors also include snow/albedo, terrain, spatial matching and observation uncertainty; they cannot all be attributed to radiative-transfer accuracy.', '',
        '### Averaging and spatial support', '',
        f'Changing the assumed Payerne minute timestamp phase by ±30 seconds spans at most {phase.max():.3f} UVI in the observed daily peak (95th percentile {phase.quantile(.95):.3f}); {support["payerne_phase_display_ambiguous"]}/{len(pay)} displayed integers are ambiguous under these bounds.', '',
        'The main comparison matches common half-hour windows. Payerne additionally supports the actual 30-minute rolling maximum sampled every five minutes:', '',
        '| Forecast day | Complete days | Rolling-peak MAE (UVI) | Within one displayed UVI | Same category |',
        '|---|---:|---:|---:|---:|']
    for r in rolling:
        lines.append(f"| {r['day']+1} | {r['n']} | {r['mae']:.3f} | {r['within_one']:.1%} | {r['same_category']:.1%} |")
    lines += ['', 'The PMOD feed does not support a direct five-minute rolling-peak observation. Agreement on common half-hour windows is therefore only partial evidence for that product.', '']
    spatial = out / 'spatial_sensitivity.json'
    if spatial.exists():
        lines += ['Predeclared alternative coordinate/cell matches, without choosing the better-scoring match:', '',
            '| Site | Forecast day | 95th percentile absolute change (UVI) | Maximum change | Category changed |',
            '|---|---:|---:|---:|---:|']
        for r in json.loads(spatial.read_text()):
            lines.append(f"| {r['site']} | {r['day']+1} | {r['p95_abs_change']:.3f} | {r['max_abs_change']:.3f} | {r['category_changed']:.1%} |")
        lines += ['', 'Surveyed instrument coordinates and terrain representativeness deserve attention before pursuing very small numerical error reductions.', '']
    lines += ['### Priority order', '',
        '1. Obtain calibrated, quality-controlled SACRaM UV for Jungfraujoch and Locarno-Monti, plus Payerne January–June 2025 instrument history and missing Weissfluhjoch periods. Raw DWH millivolts are insufficient.',
        '2. Resolve instrument coordinates, heights, averaging conventions and calibration history. Then replay the existing frozen cases; keep any subsequent calibration study separate from its held-out evaluation.',
        '3. Replay current production snow-fraction inputs across snow-covered and snow-free Alpine cases. The primary automatic snow-depth series is absent at Weissfluhjoch; nearby/manual snow depth would be supplementary context, not measured UV albedo or snow fraction.',
        '4. Prioritize cloud/shortwave and spatial-support improvements; evaluate raw errors, displayed integers, category boundaries and severe underestimation together. No single global albedo or post-hoc bias correction is selected here.',
        '5. Run a prospective season-spanning replay with frozen map-product rules and complete daylight/QC checks before public operational qualification. Regional elevation-band aggregation still needs independent observational support.', '',
        'Severe underestimation is not absent: the native experiment underestimates by at least two categories on 2/292 Davos site-days and 4/199 Weissfluhjoch site-days; Payerne has 0/92. Only two Weissfluhjoch site-days reach the displayed extreme category, so this campaign cannot qualify extreme-UV performance.', '']
    return lines


def run(root):
    out=root/'results';d=pd.read_csv(out/'daily_pairs.csv');scores=pd.read_csv(out/'scores.csv')
    g=d[(d.reason=='usable')&(d['product']=='native')]
    sites=['Davos','Weissfluhjoch','PAY'];labels={'Davos':'Davos (1610 m)','Weissfluhjoch':'Weissfluhjoch (2540 m)','PAY':'Payerne (493 m sensor)'}
    colors={'DJF':'#3274a1','MAM':'#5f9e6e','JJA':'#d98525','SON':'#9c639c'}
    upper=max(14,float(np.ceil(g[['observed_uvi','predicted_uvi']].max().max()+1)))
    fig,axes=plt.subplots(2,3,figsize=(12,8),sharex=True,sharey=True,layout='constrained')
    for day in (0,1):
        for col,site in enumerate(sites):
            ax=axes[day,col];x=g[(g.site==site)&(g.day==day)]
            for season,color in colors.items():
                y=x[x.season==season];ax.scatter(y.observed_uvi,y.predicted_uvi,s=19,c=color,label=season,alpha=.8)
            ax.plot([0,upper],[0,upper],color='#333333',lw=1);ax.fill_between([0,upper],[-1,upper-1],[1,upper+1],color='gray',alpha=.10)
            ax.set(xlim=(0,upper),ylim=(0,upper),title=f'{labels[site]} · day {day+1} · n={len(x)}',xlabel='Observed peak UVI',ylabel='Predicted peak UVI')
            ax.grid(alpha=.15)
    axes[0,0].legend(frameon=False,fontsize=8)
    fig.suptitle('Matched half-hour-grid daily peaks · fixed UV albedo 0.05\nComplete daylight days · provisional observations · grey band: ±1 raw UVI',fontsize=14)
    fig.savefig(out/'daily_scatter.png',dpi=180);plt.close(fig)
    native=d[d['product']=='native'].copy();native['month']=native.valid_date.str[:7]
    months=sorted(native.month.unique());matrix=[]
    for site in sites:
        s=native[native.site==site];matrix.append([float((s[s.month==m].reason=='usable').mean()) for m in months])
    fig,ax=plt.subplots(figsize=(13,2.8),layout='constrained')
    im=ax.imshow(matrix,aspect='auto',vmin=0,vmax=1,cmap='YlGnBu');ax.set_yticks(range(3),[labels[s] for s in sites]);ax.set_xticks(range(len(months)),months,rotation=60,ha='right')
    ax.set_title('Fraction of planned site-days with complete usable daily comparisons\nPayerne excludes January–June 2025 instrument-history gaps; zero is not zero UV')
    fig.colorbar(im,ax=ax,label='Usable fraction');fig.savefig(out/'coverage.png',dpi=180);plt.close(fig)
    table=scores[(scores.target=='daily_halfhour_grid')&(scores.stratum=='site/day/product')&(scores['product']=='native')]
    lines=['# Broader Swiss UV validation','',
      'This is a provisional, fixed-method observational assessment across the existing 150 ICON dates, August 2024–August 2026. It does not certify a public forecast product. All earlier frozen studies are preserved.','',
      '## Daily results','',
      'Daily maxima use the same observed and predicted half-hour windows. Missing daylight rejects a daily maximum. Values below are for fixed UV albedo 0.05, not an exact historical replay of production SNOWC.','',
      '| Site | Forecast day | Complete days / 150 | MAE (UVI) | Bias (UVI) | Within one displayed UVI | Same category |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for r in table.itertuples():
        lines.append(f'| {labels[r.site]} | {int(r.day)+1} | {int(r.n)} / 150 | {r.mae:.3f} | {r.bias:+.3f} | {r.within_one:.1%} | {r.same_category:.1%} |')
    lines+=['','![Daily comparison](daily_scatter.png)','','![Coverage](coverage.png)','',
      '## Sources and exclusions','',
      '| Location | Available measurement route | Treatment |',
      '|---|---|---|',
      '| Davos | PMOD/WRC via the Medical University Innsbruck UV network; existing WOUDC instrument 1492 | Provisional scored site. The feeds are not counted as independent stations. |',
      '| Weissfluhjoch | PMOD/WRC via the same UV network | Provisional scored site; substantial 2026 archive gaps. |',
      '| Payerne | Vuilleumier/MeteoSwiss monthly UV and colocated SW data in BSRN/PANGAEA | Preserved 84-date reservation; score named-instrument months only. January–June 2025 stays excluded. |',
      '| Jungfraujoch | DWH raw UV voltages | Corrected series absent in tested requests; not scored as UV. |',
      '| Locarno-Monti | DWH raw UV voltages | Corrected series absent in tested requests; not scored as UV. |','',
      'The national DWH bounding-box probes found the four SACRaM raw UV streams and no additional global erythemal measurement locations. This is a bounded search, not proof that no other Swiss instrument exists. UVClim model output, UVA-only instruments, ozone/PFR channels and planned sites are not reference UV-Index observations.','',
      'DWH provided shortwave/sunshine/snow observations for all 150 two-day requests. Corrected one-minute UV, its QC fields, and the older ten-minute biometer field contained no values in those requests. Raw millivolts were retained for availability checks only; no guessed calibration was applied.','',
      'The PMOD feed gives explicit UVI units and the publisher’s JavaScript identifies timestamp-centred half-hour windows. It has no sample QC or serial history. Its Davos overlap with WOUDC is quantified in `../imed_woudc_crosscheck.json`; feed agreement does not prove instrument independence.','',
      'Payerne uses published W/m² × 40, with Solar Light 501A and MeteoSwiss erythemal definitions. Its minute start/centre/end convention remains uncertain. The central adapter uses centred minute means; ±30-second phase bounds are retained in every complete daily row. Nonfinite/negative values, broken temporal support and inconsistent mean/min/max/std exclude windows independently of model error. No fitting was performed.','',
      '## Interpretation limits','',
      'Published PMOD coordinates are coarse and differ from the WOUDC/SMN coordinates. Native cells are selected from the stated UV feed coordinates, not assumed to coincide with SMN cells. The Weissfluhjoch selected terrain is about 346 m below the stated instrument; pressure is adjusted to instrument altitude, but this cannot correct local cloud or terrain effects. Resolve surveyed instrument coordinates before operational qualification.','',
      'The fixed 0.05/0.15/0.8 albedo experiments separate sensitivity from production performance. The historical archive lacks the production snow-fraction diagnostic. In particular, a snow-site bias under 0.05 is not by itself a measured error of the production snow treatment.','',
      'Measured-SW substitutions at Davos and Weissfluhjoch use nearby DWH stations. At Payerne they use BSRN colocated shortwave. Missing daylight SW excludes the affected windows and prevents a complete daily attribution score. These substitutions diagnose cloud/shortwave contributions; they do not remove observation or spatial-representativeness uncertainty.','',
      'Confidence intervals resample dates in season-stratified blocks of three selected campaign dates (approximately fifteen days), 2,000 replicates. Half-hour records are not independent days. Small seasonal/category samples and zero observed severe errors cannot establish zero future risk.','',
      '## Reproducibility','',
      '`scores.csv` contains per-site, forecast-day, season, year, snow, sunshine and configuration strata, plus paired half-hour and central-sun diagnostics. `confidence.json` and `paired_comparisons.json` retain date-block uncertainty and paired method contrasts. `coverage.csv` retains every exclusion; `verification.json` records independent source/arithmetic checks. Native GRIB, CAMS, DWH and UV acquisitions retain source identities and hashes.','',
      'Plans: `analysis/SWISS_UV_PROTOCOL.md` and `analysis/PAYERNE_EXPLORATORY_PROTOCOL.md`. Run `PYTHONPATH=. python analysis/swiss_uv_analysis.py --root work/swiss-uv-sites-20260906`, then the verification and report scripts with the same root.','',
      '## Primary sources','',
      '- [PMOD/WRC sites and instruments](https://www.pmodwrc.ch/en/world-radiation-center-2/wcc-uv/measurement-sites-wccuv/).',
      '- [Medical University Innsbruck UV network](https://www.uv-index.at/about/) and [site metadata](https://uv-data.i-med.ac.at/public/sites/).',
      '- [MeteoSwiss UV measurement network](https://www.meteoswiss.admin.ch/weather/measurement-systems/atmosphere/radiation-monitoring-network/uv-measurements.html).',
      '- [Solar Light 501 biometer definition](https://www.solarlight.com/product/uvb-biometer-model-501-radiometer).',
      '- [BSRN file definitions](https://bsrn.awi.de/data/station-to-archive-file-format/) and [data/QC conditions](https://bsrn.awi.de/data/conditions-of-data-release/).',
      '- Payerne observations: Laurent Vuilleumier, MeteoSwiss; World Radiation Monitoring Center/BSRN, PANGAEA. Each monthly DOI and instrument history is cited in `../payerne/acquisition.json`.','']
    lines += interpretation(root, d)
    (out/'report.md').write_text('\n'.join(lines))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    run(p.parse_args().root)
