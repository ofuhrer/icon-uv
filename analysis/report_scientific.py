"""Scientific figures, canonical report payload, and notebook companion.

Uses Matplotlib for standalone scientific exports. The installed report skill's
portable builder renders artifact.json; this script does not implement HTML.
"""
from pathlib import Path
import base64
import json
import sqlite3

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import nbformat

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/scientific-hardening-20260906/results'
BLUE='#2563A6'; GOLD='#B87918'; INK='#25303B'
TITLE='Expanded scientific validation of ICON UV'


def figures():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
        'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18,'figure.facecolor':'white'})
    def save(fig,name):
        fig.savefig(OUT/(name+'.png'),dpi=165,bbox_inches='tight')
        fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight')
        plt.close(fig)
    stats=pd.read_csv(OUT/'forecast_primary.csv',dtype={'cycle':str})
    d=stats[(stats.cycle=='00')&(stats.n>0)].pivot(index='site',columns='product',values='mae')
    d=d.sort_values('forecast_uvi')
    fig,ax=plt.subplots(figsize=(10,6.6),layout='constrained');y=np.arange(len(d))
    ax.barh(y+.18,d.forecast_uvi,.34,color=BLUE,label='Current cloud inversion')
    ax.barh(y-.18,d.gray_forecast_uvi,.34,color=GOLD,label='Unfitted gray-cloud baseline')
    ax.set(yticks=y,yticklabels=d.index,xlabel='Mean absolute error (UVI)',xlim=(0,3.6))
    ax.legend(loc='lower right',frameon=False)
    fig.suptitle('UV forecast error at 14 sites on 5 September 2026\n00 UTC ICON cycle; 08–16 UTC; eight matched hours per site',fontsize=13)
    save(fig,'forecast_baseline')

    daily=pd.read_csv(OUT/'historical_daily.csv')
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharey=True,layout='constrained')
    dates=sorted(daily.date.unique());x=np.arange(8)
    for ax,site in zip(axes,['Davos','Weissfluhjoch']):
        d=daily[(daily.site==site)&daily['product'].isin(['reference_uvi','gray_uvi'])]
        counts=d[d['product']=='reference_uvi'].set_index('date').reindex(dates).n
        for offset,product,label,color in [(-.18,'reference_uvi','RT inversion',BLUE),(.18,'gray_uvi','Gray-cloud baseline',GOLD)]:
            values=d[d['product']==product].set_index('date').reindex(dates).bias
            ax.bar(x+offset,values,.34,color=color,label=label)
        for i,count in enumerate(counts):
            if count==0: ax.text(i,.04,'No UV',rotation=90,ha='center',va='bottom',color='#777777',fontsize=9)
        ax.axhline(0,color=INK,lw=1)
        labels=[pd.Timestamp(date).strftime('%d %b')+f'\nn={int(count)}' for date,count in zip(dates,counts)]
        ax.set(xticks=x,xticklabels=labels,ylabel='Mean error (UVI)',title=site,ylim=(-.3,1.4))
    axes[0].legend(frameon=False,loc='upper right')
    fig.suptitle('Historical conversion errors, 29 August–5 September 2026\nNearby measured SW and pressure; assumed albedos; 08–16 UTC; n = usable hourly pairs',fontsize=12)
    save(fig,'historical_daily')

    sw=pd.read_csv(OUT/'regional_regimes.csv',dtype={'cycle':str});sw=sw[sw.cycle=='00']
    paired=pd.read_csv(OUT/'paired_cycle_summary.csv')
    fig,axes=plt.subplots(1,2,figsize=(12,6.7),layout='constrained')
    order=['0–5 min sunshine','Intermediate sunshine','50–60 min sunshine','Unknown sunshine']
    sw=sw.set_index('sunshine_regime').loc[order]
    axes[0].bar(np.arange(4),sw.bias,color=[BLUE,'#7A95AC',GOLD,'#AAAAAA'])
    axes[0].axhline(0,color=INK,lw=1)
    axes[0].set(xticks=np.arange(4),xticklabels=[f'0–5 min\nn={int(sw.n.iloc[0])}',f'>5, <50 min\nn={int(sw.n.iloc[1])}',f'50–60 min\nn={int(sw.n.iloc[2])}',f'Unknown\nn={int(sw.n.iloc[3])}'],ylabel='Mean shortwave bias (W/m²)',xlabel='Measured sunshine per hour',title='00 UTC forecast, 08–16 UTC',ylim=(-125,185))
    axes[0].text(.02,.96,'135 stations; missing sunshine is explicit.\nSource: MeteoSwiss.',transform=axes[0].transAxes,va='top',fontsize=9)
    sites=sorted(paired.site.unique()); y=np.arange(len(sites))
    for comparison,color,marker,label in [('00_vs_06',BLUE,'o','06 minus 00 UTC: 08–16 UTC'),('00_vs_12',GOLD,'s','12 minus 00 UTC: 13–16 UTC')]:
        d=paired[paired.comparison==comparison].set_index('site').reindex(sites)
        axes[1].scatter(d.delta_mae,y,c=color,marker=marker,s=32,label=label)
    axes[1].axvline(0,color=INK,lw=1)
    axes[1].set(yticks=y,yticklabels=sites,xlabel='Change in MAE (UVI); negative = improved',title='UV cycles on identical site-hour pairs',xlim=(-.5,.4))
    axes[1].legend(loc='lower right',frameon=False,fontsize=8)
    fig.suptitle('Shortwave regimes and matched forecast-cycle differences\n5 September 2026; common CAMS composition held fixed across ICON cycles',fontsize=12)
    save(fig,'regimes_and_cycles')


def sections():
    return [
('summary', '''## Technical summary
The expanded evidence strengthens the adverse mountain finding and exposes a limitation of the current cloud inversion: a simple unfitted gray-cloud baseline has lower forecast MAE in this case. The analysis now covers 14 UV sites with complete primary-window observations, three ICON cycles, 135 shortwave stations, and a separate eight-day radiation-conversion experiment at two Swiss sites.

**Assessment: reproducible scientific case studies with explicit limitations; operational UV skill remains unvalidated.** The newer cycles are not uniformly better, and neither the cloud inversion nor a single bias correction can be justified from these cases. No parameters were fitted and the production forecast algorithm was not changed.'''),
('scope', '''## Evaluation design and definitions
The [protocol](https://opendatadocs.meteoswiss.ch/e-forecast-data/e2-e3-numerical-weather-forecasting-model) uses a fixed 08–16 UTC primary window, independent of observed UVI. The repository file `analysis/SCIENTIFIC_PLAN.md` was written before scoring the expanded results. The original four-site case was already known, so this extension is not presented as a completely unseen benchmark.

**Forecast evaluation:** 5 September 2026 ICON-CH2 control runs at 00, 06 and 12 UTC, with CAMS composition fixed to 4 September 12 UTC. Holding CAMS fixed isolates changes in ICON forcing/state; it is not a full operational forecast-cycle comparison or proof of issue-time data availability. Each UV site uses its nearest native cell within 10 km; all 20 listed sites are geometrically covered, at distances no greater than 1.46 km. Fourteen sites have eight usable UV pairs during 08–16 UTC. Bratislava, Dornbirn, Innsbruck, Leifers, Mariapfarr and Ritten have no usable pair in this window. They remain in the coverage tables with explicit exclusions.

**Historical experiment:** 29 August–5 September at Davos and Weissfluhjoch. Nearby measured global shortwave and surface pressure are combined with the previous day's 12 UTC CAMS composition. This is observation-driven radiation conversion, not historical ICON forecast skill. Reference shortwave/UV albedos are explicitly assumed to be 0.15/0.05; other surfaces are sensitivities, not inferred actual conditions.

Reported UV values at :15 and :45 are averaged to approximate an hourly mean. Their current averaging bounds and per-value QC remain unconfirmed. SwissMetNet timestamps are confirmed UTC interval ends. Positive bias means prediction minus observation. MAE and RMSE use paired hourly errors, with equal weight per retained pair. Relative mean excess is the ratio of sums minus one, not a mean of hourly percentages. Dose errors, where reported, refer only to the matched intervals, with 1 UVI-hour = 90 J/m² of erythemally weighted radiant exposure. No numerical pass/fail threshold was invented.'''),
('forecast', '''## Fourteen-site verification confirms large mountain errors
For the 00 UTC forecast, each usable site contributes eight hours. Mean UVI biases include **Sonnblick +3.02**, **Weissfluhjoch +1.95**, **Zugspitze +1.82**, **Davos +1.70**, and **Aosta +0.40**. Sonnblick's mean prediction is 5.27 versus 2.25 reported (+134%). All 14 site-mean biases are positive, although individual hourly errors can have either sign.

The current inversion's pooled MAE is **1.072 UVI**, versus **0.855 UVI** for the unfitted gray-cloud baseline on the same 112 pairs. The baseline multiplies modeled clear-sky UVI by incoming shortwave divided by modeled clear-sky shortwave. It uses identical atmospheric inputs and no observed UV calibration.

This comparison does not establish that gray attenuation is physically superior. It may compensate for excessive shortwave forcing, while the current inversion represents the spectral difference between broadband and erythemal attenuation. Added forecast skill from that inversion has not been demonstrated here. Any algorithm change should be evaluated on separate weather cases.'''),
('cycles', '''## Matching hours prevents a misleading cycle comparison
For 00 versus 06 UTC, 14 sites share 112 pairs over 08–16 UTC. Pooled MAE falls from **1.072 to 1.008 UVI**, a change of −0.064. Ten sites improve and four worsen. For 00 versus 12 UTC, the common support is only 13–16 UTC: 42 pairs. On those exact pairs, MAE rises from **0.585 to 0.667 UVI**, a change of +0.082. Four sites improve and ten worsen. Comparing the full 00 UTC window to the shorter 12 UTC window would incorrectly make the improvement appear much larger.

The corresponding shortwave comparison also shows small and inconsistent changes: MAE falls from 135.26 to 133.36 W/m² for 00 versus 06 UTC (1,080 identical pairs), but rises from 105.60 to 106.25 W/m² for 00 versus 12 UTC (405 identical afternoon pairs). These paired results describe this case, not a general lead-time dependence.'''),
('regimes', '''## Shortwave error changes sign with measured sunshine
The 00 UTC run retains the earlier regional bias of **+64.25 W/m²** across 135 stations and 1,080 hours. Stratifying by measured sunshine makes the aggregate more informative:

| Sunshine in an hour | Station-hours | Mean SW bias |
|---|---:|---:|
| 0–5 minutes | 427 | +150.19 W/m² |
| More than 5, less than 50 minutes | 454 | +38.26 W/m² |
| 50–60 minutes | 167 | −79.11 W/m² |
| Unknown sunshine | 32 | +34.35 W/m² |

Four stations lack sunshine metadata; their 32 hours remain in the radiation total but are not assigned a measured-sunshine regime. This pattern is consistent with errors in cloud amount or placement, but sunshine is a local radiation-derived proxy, not an independent map of cloud truth. Station-hours share the same weather situation and are correlated. A universal downward correction could worsen sunny-hour errors.'''),
('history', '''## Residual conversion errors persist across several days
In the historical experiment, all 128 requested daylight station-hours have shortwave/pressure drivers, but UV gaps leave **49/64 hours at Davos** and **37/64 at Weissfluhjoch**. Davos has data on seven days, six complete; Weissfluhjoch on five days, four complete. Missingness is substantial and is not treated as random.

| Site | Usable hours | RT bias | RT MAE | Gray-baseline MAE |
|---|---:|---:|---:|---:|
| Davos | 49 | +0.314 UVI | 0.355 UVI | 0.351 UVI |
| Weissfluhjoch | 37 | +0.622 UVI | 0.622 UVI | 0.534 UVI |

Relative mean excess is about 8.1% and 15.8%. Equal weighting of available daily mean errors gives +0.327 and +0.666 UVI. Leaving out each day with usable data yields mean-bias ranges of **+0.297 to +0.355** and **+0.533 to +0.699**. These are sensitivity ranges, not confidence intervals. Partial days are explicitly marked in the figure.

For hours with 0–5 minutes of sunshine, RT MAE is 0.196 UVI at Davos (seven pairs) and 0.324 at Weissfluhjoch (six pairs); the gray baseline gives 0.328 and 0.138. Neither method wins consistently across sites and regimes. These small subgroups support diagnosis, not method selection.'''),
('robustness', '''## Numerical and scientific robustness
Increasing solar samples from four to twelve changes the reconstructed site forecasts by at most **0.00213 UVI** across the three cycles. Thus solar quadrature is much smaller than the observed errors in this evaluation; that does not test within-hour cloud evolution or certify true subhourly maxima.

The historical reference calculation uses measured QFE pressure converted from hPa to Pa, then adjusted from barometer height to published UV height with a fixed 8,434 m scale height. This differs deliberately from the earlier same-cell shortwave substitution. Scores from the two experiments should not be mixed because surface state and primary cohorts differ.

Dark-surface assumptions (SW/UV albedos 0.05/0) give mean errors +0.287 and +0.596 UVI; a brighter-soil scenario (0.30/0.15) gives +0.393 and +0.704. A snow scenario (0.60/0.80) greatly increases UVI and is not evidence that snow was present. No albedo was chosen by optimizing agreement. Composition is from CAMS, not an independent ozone/aerosol measurement.

Measured SW exceeds the modeled reference clear-sky SW in 16 usable hours at each Swiss site. The existing above-clear scaling flag is retained and reported; maximum measured/model-clear ratios are 1.131 at Davos and 1.069 at Weissfluhjoch. These cases could reflect atmosphere/surface assumptions, cloud enhancement, site representation or measurement effects. They prevent treating modeled clear-sky radiation as verified truth.

Splitting by observation age does not establish a simple data-quality explanation. Among available observations at least five calendar days old, mean residuals remain +0.251 UVI at Davos and +0.965 at Weissfluhjoch. Age is not a substitute for actual QC status, and these groups have different weather and missingness.'''),
('sources', '''## Observation provenance and strengthened safeguards
The [PMOD/WRC site documentation](https://www.pmodwrc.ch/en/world-radiation-center-2/wcc-uv/measurement-sites-wccuv/) confirms the 1,610 m Davos roof installation and 2,540 m Weissfluhjoch SLF UV site. The nearby SwissMetNet stations are at 1,594 m and 2,691 m. Approximate separations are 1.77 km and 1.10 km; the coarse published UV coordinates are not improved by guessing. Both PMOD sites have colocated SW instrumentation, but a current machine-readable delivery of that colocated record was not obtained. The SwissMetNet replacement therefore remains a nearby-station diagnostic.

The [network's peer-reviewed methodology](https://acp.copernicus.org/articles/8/7483/2008/) documents historical calibration and 10/30-minute measurement practices. It does not certify the 2026 API values, their exact timestamps, or the current calibration of each instrument. All four original Swiss/partner UV series match the newer API retrieval at their common timestamps; lack of a revision is not proof of QC completion.

The extension freezes **179 input hashes before evaluation** and verifies them on every replay. It rejects duplicate timestamps and conflicting source revisions, preserves missing pairs, records named site identities and model distances, and stores production/analysis code hashes and package versions. Expected hashes are never regenerated from inputs during a validation check. Float32 forecast values are promoted before CSV export so independently recomputed scores retain their original precision.

**Source: MeteoSwiss** for ground radiation, sunshine, pressure, metadata and ICON. [Timestamp documentation](https://opendatadocs.meteoswiss.ch/general/download); [quality-control FAQ](https://opendatadocs.meteoswiss.ch/general/faq); [public UV API](https://uv-data.i-med.ac.at/public/data/?product=uve&start=2026-08-29&stop=2026-09-06); [CAMS dataset](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts).'''),
('limits', '''## Validation boundary and next work
The original mountain discrepancy is reinforced, but **operational readiness is not established**. The main residual barriers are independent calibrated UV metadata, colocated radiation, missing observations, a single forecast weather day, and incomplete regime/season coverage. The 4 September forecast query returned no data under the public 24-hour retention policy. It was not replaced with a later initialization or reanalysis and labeled a forecast.

The historical experiment is broader in time but conditional on observed SW and pressure; it cannot measure end-to-end forecast skill. Neither temporal screening, within-hour cloud maxima, snow-albedo treatment, long-term calibration stability nor a full seasonal hindcast is observationally validated. No iid confidence intervals or significance claims are made from correlated station-hours.

Next, obtain documented colocated UV/SW records and calibration/QC/averaging metadata; assemble an archive of distinct forecast weather days and issue-time inputs; predefine seasonal/regime benchmarks and hold out evaluation cases. Test corrections and alternative cloud representations against both the current inversion and the gray baseline. Do not infer a universal correction from the present positive average errors.'''),
('questions', '''## Questions raised by the expanded evidence
Does the gray baseline win after shortwave forcing errors are removed at truly colocated instruments? Are the large high-altitude errors associated with clouds below the station that the effective uniform-cloud approximation cannot represent? How much of the persistent Weissfluhjoch residual follows spatial separation and surface assumptions? Do sunny/low-sun/snow regimes and independent seasons reverse the ranking?'''),
('reproduce', '''## Reproducibility and delivery checks
Repository code: `analysis/scientific.py`, `analysis/fetch_scientific.py`, `analysis/verify_scientific.py`, `analysis/report_scientific.py`, and `analysis/SCIENTIFIC_PLAN.md`. The local data directory is `work/scientific-hardening-20260906`; results, figures, report and executed notebook are in its `results` subdirectory. The notebook is `expanded_scientific_validation.ipynb`; PNG and PDF figures are exported alongside it. Reproduction instructions are in `analysis/README.md`.

The notebook checks frozen inputs, executes the calculations and independent reconciliation, and regenerates the figures. The raw CSV/JSON and normalized forecast/GRIB inputs remain local ignored artifacts; the tracked scripts and methodological summary are durable repository changes. Live rolling observation URLs may change, so replay uses archived files. No production forecast algorithm or empirical calibration was changed for this extension.

The HTML reader is packaged by the installed report builder. Scientific plots are Matplotlib exports; payload/schema and structural checks are performed. Interactive HTML controls are not claimed browser-verified when browser automation is unavailable. The executed notebook and standalone figures are the computational and visual audit trail.''')]


def build():
    OUT.mkdir(parents=True,exist_ok=True);figures()
    sections_list=sections()
    # Correct source label: this is an archive policy link, not the local protocol.
    sections_list=[(key,body.replace('The [protocol](https://opendatadocs.meteoswiss.ch/e-forecast-data/e2-e3-numerical-weather-forecasting-model) uses','The evaluation protocol uses')) for key,body in sections_list]
    blocks=[{'id':'title','type':'markdown','body':'# '+TITLE}]
    for ident,body in sections_list:
        blocks.append({'id':ident,'type':'markdown','body':body})
        if ident=='forecast':blocks.append({'id':'baseline_chart','type':'chart','chartId':'baseline'})
        selected={'forecast':('forecast_baseline','Forecast MAE at all 14 usable sites; current inversion and unfitted baseline.'),
                  'regimes':('regimes_and_cycles','Shortwave errors by sunshine and paired UV cycle differences; valid-time windows are explicit.'),
                  'history':('historical_daily','Historical daily residuals with usable hourly counts; missing days are not zero errors.')}.get(ident)
        if selected:
            name,caption=selected;encoded=base64.b64encode((OUT/(name+'.png')).read_bytes()).decode()
            blocks.append({'id':name,'type':'html','body':f'<figure><img src="data:image/png;base64,{encoded}" alt="{caption}" style="width:100%;height:auto"><figcaption>{caption}</figcaption></figure>'})
    connection=sqlite3.connect(':memory:')
    frame=pd.read_csv(OUT/'forecast_pairs.csv',dtype={'cycle':str});frame.to_sql('forecast_pairs',connection,index=False)
    query="""WITH predictions AS (
SELECT site, cycle, hour, observed_uvi, forecast_uvi AS predicted, 'Current inversion' AS calculation FROM forecast_pairs
UNION ALL
SELECT site, cycle, hour, observed_uvi, gray_forecast_uvi, 'Gray-cloud baseline' FROM forecast_pairs)
SELECT site, calculation, COUNT(*) AS hours, AVG(predicted-observed_uvi) AS bias_uvi,
AVG(ABS(predicted-observed_uvi)) AS mae_uvi, AVG(observed_uvi) AS mean_reported_uvi,
AVG(predicted) AS mean_predicted_uvi
FROM predictions WHERE cycle='00' AND hour>=8 AND hour<16 AND observed_uvi IS NOT NULL
GROUP BY site, calculation ORDER BY site, calculation"""
    data=pd.read_sql_query(query,connection);connection.close()
    (OUT/'forecast_baseline.sql').write_text(query+'\n')
    source={'id':'analysis','label':'Fixed-cohort forecast pairs; public UV observations and ICON/CAMS',
            'path':'analysis/scientific.py','query':{'sql':query,'language':'sql','engine':'SQLite',
            'description':'Actual report aggregation over reviewed pairs; upstream production, alignment and exclusions are in the preserved Python source.',
            'tables_used':['forecast_pairs'],'filters':['ICON cycle 5 September 2026 00 UTC','08–16 UTC','Finite complete observed pairs; no observed-UVI threshold'],
            'metric_definitions':['MAE = mean(abs(predicted - observed UVI))','Bias = mean(predicted - observed UVI)','Eight hourly pairs per included site'],
            'upstream_python':(ROOT/'analysis/scientific.py').read_text()}}
    artifact={'surface':'report','manifest':{'version':1,'title':TITLE,'blocks':blocks,'sources':[source],
               'charts':[{'id':'baseline','title':'Forecast UVI MAE by site and calculation, 5 September 2026','type':'bar','dataset':'baseline','sourceId':'analysis',
                          'encodings':{'x':{'field':'site'},'y':{'field':'mae_uvi','label':'MAE (UVI)'},'color':{'field':'calculation'}},'options':{'grouping':'grouped'}}]},
              'snapshot':{'version':1,'status':'ready','datasets':{'baseline':json.loads(data.to_json(orient='records'))}}}
    (OUT/'artifact.json').write_text(json.dumps(artifact,indent=2,allow_nan=False)+'\n')
    (OUT/'report.md').write_text('# '+TITLE+'\n\n'+'\n\n'.join(body for _,body in sections_list)+'\n')
    # A concise, tracked scientific record survives cleanup of the ignored data.
    # Reviewed findings under analysis/ are maintained separately from generated reports.
    path=OUT/'expanded_scientific_validation.ipynb'
    if path.exists(): return
    md=nbformat.v4.new_markdown_cell;code=nbformat.v4.new_code_cell;content=dict(sections_list)
    nb=nbformat.v4.new_notebook()
    nb.metadata.kernelspec={'display_name':'Python (scientific analysis)','name':'python3','language':'python'}
    nb.cells=[md('# '+TITLE+'\n\n## tl;dr\n'+content['summary'].split('\n',1)[1]),
              md('## Context & Methods\n'+content['scope'].split('\n',1)[1]+'\n\n### Key assumptions\nObservation averaging/QC are unconfirmed; SW instruments are nearby; historical albedos are assumed; no fitting or independent station-hour confidence interval.'),
              code("from pathlib import Path\nimport sys\nROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'analysis/scientific.py').is_file())\nsys.path.insert(0, str(ROOT))\nimport pandas as pd\nfrom IPython.display import display, Image\nfrom analysis import scientific, verify_scientific, report_scientific\nOUT = scientific.OUTPUT"),
              md('## Data\nVerify the previously frozen input manifest before computing; changed or missing inputs stop the replay.'),
              code("manifest=scientific.verify_inputs()\nprint('Verified frozen inputs:',len(manifest['inputs']))\nprint('Frozen at:',manifest['frozen_at'])"),
              md('## Results\n### Reproduce the calculations\nNo network requests, interpolation of missing observations, or fitting occur.'),
              code('forecast,historical=scientific.run()\nverification=verify_scientific.check()\ndisplay(verification)\nreport_scientific.figures()'),
              md('### Forecast coverage and baseline comparison\n'+content['forecast'].split('\n',1)[1]),
              code("scores=pd.read_csv(OUT/'forecast_primary.csv',dtype={'cycle':str})\ndisplay(scores[(scores.cycle=='00') & (scores['product']=='forecast_uvi')][['site','eligible_rows','excluded_nonfinite','n','bias','mae']])\ndisplay(Image(filename=str(OUT/'forecast_baseline.png')))"),
              md('### Paired forecast cycles and shortwave regimes\n'+content['cycles'].split('\n',1)[1]),
              code("paired=pd.read_csv(OUT/'paired_cycle_errors.csv')\ndisplay(paired.groupby('comparison')[['base_absolute_error','new_absolute_error','delta_absolute_error']].mean())\ndisplay(pd.read_csv(OUT/'regional_paired_summary.csv'))\ndisplay(Image(filename=str(OUT/'regimes_and_cycles.png')))"),
              md('### Historical conversion and missingness\n'+content['history'].split('\n',1)[1]),
              code("display(pd.read_csv(OUT/'historical_summary.csv'))\ndisplay(pd.read_csv(OUT/'historical_day_distribution.csv'))\ndisplay(Image(filename=str(OUT/'historical_daily.png')))"),
              md('### Robustness\n'+content['robustness'].split('\n',1)[1]),
              code("display(pd.read_csv(OUT/'historical_flags.csv'))\ndisplay(pd.read_csv(OUT/'historical_age_groups.csv'))\nprint('Maximum quadrature change:',forecast.quadrature_delta.abs().max())\ndisplay(pd.read_csv(OUT/'leave_one_day_out.csv'))"),
              md('## Takeaways\n'+content['limits'].split('\n',1)[1]+'\n\n'+content['sources']+'\n\n'+content['questions'])]
    nbformat.write(nb,path)


if __name__=='__main__': build()
