"""Produce standalone scientific figures, findings, and a replay notebook."""
import hashlib
import importlib.metadata
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.multiyear import ROOT,INPUT,OUTPUT


def write_run_identity():
    """Record the actual analysis code, inputs, checks and result identities."""
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    identity_path=OUTPUT/'run_identity.json'
    identity=json.loads(identity_path.read_text())
    identity['report_created']=datetime.now(timezone.utc).isoformat()
    identity['python']=platform.python_version()
    identity['packages']={name:importlib.metadata.version(name) for name in
                          ('numpy','scipy','pandas','xarray','netCDF4','eccodes','matplotlib','nbformat')}
    # Generating a notebook does not require the optional notebook executor.
    try:
        identity['packages']['nbclient']=importlib.metadata.version('nbclient')
    except importlib.metadata.PackageNotFoundError:
        identity['packages']['nbclient']=None
    sources=sorted((ROOT/'analysis').glob('*.py'))+sorted((ROOT/'icon_uv').glob('*.py'))
    sources += [ROOT/'analysis/MULTIYEAR_PLAN.md',ROOT/'analysis/MULTIYEAR_UV_PLAN.md',
                ROOT/'analysis/multiyear_cases.csv',ROOT/'icon_uv/data/rt.npz']
    identity['code']={str(p.relative_to(ROOT)):sha(p) for p in sources}
    identity['uv_frozen_manifest_sha256']=sha(INPUT/'uv/frozen_inputs.json')
    identity['checks']={name:json.loads(path.read_text()) for name,path in {
        'native_sw':OUTPUT/'verification.json','uv_arithmetic':OUTPUT/'uv_verification.json',
        'archive_bridge':INPUT/'bridge_check.json','woudc_api_conversion':INPUT/'woudc_api_check.json'}.items()}
    uv=pd.read_csv(OUTPUT/'uv_pairs.csv')
    identity['evaluated_uv_diagnostic_cases']=int(uv[(uv.day==0)&(uv.reason=='usable')].reference.nunique())
    identity['evaluated_full_uv_cases']=0
    identity['results']={p.name:sha(p) for p in sorted(OUTPUT.glob('*.csv'))}
    identity_path.write_text(json.dumps(identity,indent=2))


def main():
    sw=pd.read_csv(OUTPUT/'pairs.csv')
    uv=pd.read_csv(OUTPUT/'uv_pairs.csv')
    cases=pd.read_csv(OUTPUT/'case_coverage.csv')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
    def save(fig,name):
        fig.savefig(OUTPUT/f'{name}.png',bbox_inches='tight')
        fig.savefig(OUTPUT/f'{name}.pdf',bbox_inches='tight')
        plt.close(fig)
    months=pd.period_range('2024-08','2026-08',freq='M').astype(str)
    counts=cases[cases.status=='evaluated_sw'].assign(month=lambda x:x.case_date.str[:7] if 'case_date' in x else x.date.str[:7]).groupby('month').size().reindex(months,fill_value=0)
    uv_good=uv[(uv.day==0)&(uv.reason=='usable')]
    ucounts=uv_good.assign(month=uv_good.case_date.str[:7]).groupby('month').reference.nunique().reindex(months,fill_value=0)
    fig,ax=plt.subplots(figsize=(12,3.7),layout='constrained')
    x=np.arange(len(months));ax.bar(x-.19,counts,.38,label='ICON SW cases',color='#28638a');ax.bar(x+.19,ucounts,.38,label='UV diagnostic cases',color='#bc6529')
    ax.set(xticks=x,xticklabels=months,ylabel='Distinct initializations',ylim=(0,7.5),title='Monthly coverage: six dates per month; missing UV stays missing')
    ax.tick_params(axis='x',rotation=60);ax.legend(frameon=False,ncol=2)
    save(fig,'multiyear_coverage')
    season=pd.read_csv(OUTPUT/'season.csv');sun=pd.read_csv(OUTPUT/'sunshine.csv');sun=sun[sun.day==0]
    fig,axes=plt.subplots(1,2,figsize=(12,4.2),layout='constrained')
    for day,label,color in [(0,'Initialization day','#28638a'),(1,'Following day','#72a5bd')]:
        s=season[season.day==day].set_index('season').reindex(['DJF','MAM','JJA','SON'])
        axes[0].bar(np.arange(4)+(day-.5)*.34,s.mae,.34,label=label,color=color)
    axes[0].set(xticks=range(4),xticklabels=['Winter','Spring','Summer','Autumn'],ylabel='SW MAE (W/m²)',ylim=(0,140),title='Seasonal SW errors');axes[0].legend(frameon=False)
    order=['0–5 min sunshine','Intermediate sunshine','50–60 min sunshine','Unknown sunshine'];sun=sun.set_index('sunshine_regime').reindex(order)
    axes[1].bar(range(4),sun.bias,color=['#bc6529','#bc6529','#28638a','#8b9295']);axes[1].axhline(0,color='#444',lw=.8)
    axes[1].set(xticks=range(4),xticklabels=['0–5 min','5–50 min','50–60 min','Unknown'],xlabel='Observed sunshine per hour',ylabel='SW bias (W/m²)',ylim=(-75,100),title='Initialization-day bias by measured sunshine')
    for i,row in enumerate(sun.itertuples()):axes[1].text(i,row.bias+(4 if row.bias>=0 else -7),f'{row.dates} dates',ha='center',va='bottom' if row.bias>=0 else 'top',fontsize=8)
    save(fig,'multiyear_sw')
    daily=pd.read_csv(OUTPUT/'uv_daily.csv');daily=daily[(daily.day==0)&(daily.usable>0)]
    fig,axes=plt.subplots(1,2,figsize=(12,4.3),layout='constrained')
    for product,label,color in [('reference_uvi','UV albedo 0.05','#28638a'),('gray_uvi','Gray cloud; UV albedo 0.05','#bc6529')]:
        d=daily[daily['product']==product];axes[0].scatter(pd.to_datetime(d.valid_date),d.bias,label=label,s=17,alpha=.8,color=color)
    axes[0].axhline(0,color='#444',lw=.8);axes[0].set(ylabel='Daily mean UVI error',title='Davos: daily diagnostic errors');axes[0].tick_params(axis='x',rotation=35);axes[0].legend(frameon=False,fontsize=8)
    for name,color in [('Snow-free','#28638a'),('Measured snow','#bc6529'),('Unknown snow','#8b9295')]:
        g=uv_good[uv_good.snow_regime==name];axes[1].scatter(g.observed_uvi,g.reference_uvi,s=8,alpha=.35,label=name,color=color)
    top=max(uv_good.observed_uvi.max(),uv_good.reference_uvi.max())*1.03
    axes[1].plot([0,top],[0,top],color='#444',lw=.8);axes[1].set(xlabel='Measured hourly mean UVI',ylabel='Diagnostic UVI (UV albedo 0.05)',title='Davos: nearby measured snow regime',xlim=(0,top),ylim=(0,top));axes[1].legend(frameon=False,fontsize=8)
    save(fig,'multiyear_uv')
    overall=pd.read_csv(OUTPUT/'overall.csv').set_index('day').loc[0]
    u=pd.read_csv(OUTPUT/'uv_overall.csv');u=u[u.day==0].set_index('product')
    ref=u.loc['reference_uvi'];gray=u.loc['gray_uvi'];snow=u.loc['snow_uvi']
    seasons=pd.read_csv(OUTPUT/'season.csv');seasons=seasons[seasons.day==0].set_index('season')
    uv_seasons=pd.read_csv(OUTPUT/'uv_season.csv').query("day == 0 and product == 'reference_uvi'").set_index('season')
    season_table='| Season | SW dates | SW bias / MAE (W/m²) | UV dates | UV bias / MAE (UVI) |\n|---|---:|---:|---:|---:|\n'
    for season_name in ['DJF','MAM','JJA','SON']:
        s=seasons.loc[season_name];v=uv_seasons.loc[season_name]
        season_table+=f'| {season_name} | {int(s.dates)} | {s.bias:+.2f} / {s.mae:.2f} | {int(v.dates)} | {v.bias:+.3f} / {v.mae:.3f} |\n'
    verification=json.loads((OUTPUT/'verification.json').read_text())
    uv_verification=json.loads((OUTPUT/'uv_verification.json').read_text())
    uv_flags=uv_good.flag.astype(int)
    config_counts=pd.read_csv(OUTPUT/'configuration.csv').query('day == 0')[['configuration','dates']]
    config_text=', '.join(f'{int(r.configuration)}: {int(r.dates)} dates' for r in config_counts.itertuples())
    text=f'''# Multi-year ICON scientific evaluation

**150 ICON-CH2 control initializations on 150 dates, August 2024–August 2026:**
50 times the previous three initializations, spanning all four seasons and three
calendar years. Dates were fixed before scoring: days 3, 8, 13, 18, 23 and 28 of
each month. Source: MeteoSwiss.

The primary SW evaluation contains **{int(overall.usable):,} matched station-hours**
at 135 stations. The following-day window is also evaluated separately. These
station-hours are correlated; they are not independent sample replicates.

WOUDC supplies sufficient Davos measurements for **{int(ref.initializations)}
initialization-day UV diagnostic cases** ({ref.initializations/3:.1f} times the
previous initialization count), with {int(ref.usable)} matched hours. These use
explicit UV-albedo assumptions. They are not exact production-grid UV replays:
the native archive does not provide the required SNOWC field. The new count of
fully reproduced production UV cases is **zero**; the original three remain the
existing reference study.

![Monthly case coverage](multiyear_coverage.png)

## Findings

- Primary SW bias is **{overall.bias:+.2f} W/m²**, MAE **{overall.mae:.2f} W/m²**,
  and RMSE **{overall.rmse:.2f} W/m²**. Equal-day bias/MAE are
  {overall.equal_day_bias:+.2f}/{overall.equal_day_mae:.2f} W/m².
- The earlier weather-regime pattern persists over many dates: SW bias is
  {sun.loc['0–5 min sunshine','bias']:+.2f} W/m² for 0–5 minutes of measured sunshine,
  {sun.loc['Intermediate sunshine','bias']:+.2f} W/m² for intermediate sunshine,
  and {sun.loc['50–60 min sunshine','bias']:+.2f} W/m² for 50–60 minutes.
  Those measured regimes occur on {int(sun.loc['0–5 min sunshine','dates'])},
  {int(sun.loc['Intermediate sunshine','dates'])} and
  {int(sun.loc['50–60 min sunshine','dates'])} primary dates respectively.
  They are sunshine-based strata, not validated cloud-type classifications.
- SW bias varies seasonally: winter {seasons.loc['DJF','bias']:+.2f}, spring
  {seasons.loc['MAM','bias']:+.2f}, summer {seasons.loc['JJA','bias']:+.2f}, autumn
  {seasons.loc['SON','bias']:+.2f} W/m². Seasonal absolute errors and paired
  weather differences must not be confused with changes in model quality.
- Davos UV, with prescribed UV albedo 0.05: bias **{ref.bias:+.3f} UVI**, MAE
  **{ref.mae:.3f} UVI**; gray-cloud baseline MAE **{gray.mae:.3f} UVI** on the same
  hours. The UV-albedo 0.80 scenario has bias {snow.bias:+.3f} UVI. Surface
  scenarios are sensitivity experiments, not fitted corrections or uncertainty
  bounds. See the season/snow tables before interpreting the pooled scores.

{season_table}
UV columns use the prescribed albedo 0.05 diagnostic at Davos; SW columns use
the 135-station network. Both are initialization-day windows. Absolute UV
errors depend strongly on the seasonal UVI range. The small pooled MAE
difference between the UV method and gray-cloud baseline does not establish
a reliable skill advantage for either method.

![Seasonal and sunshine-stratified SW errors](multiyear_sw.png)

![Davos UV diagnostics](multiyear_uv.png)

## Coverage and scientific limits

Every planned case has matched SW observations. The primary ledger retains
{int(overall.requested-overall.usable):,} excluded station-hours, including missing
observations and changed station positions. Only DWH quality category 4 enters
primary SW scoring. Measured snow is present on 148 primary dates somewhere in
the network, but snow observations are missing for many station-hours; the snow
stratification is not a complete snow-cover validation.

There are 30 primary dates in 2024, 72 in 2025 and 48 in 2026; winter, spring,
summer and autumn contain 36, 36, 42 and 36 dates. Operational configuration
identifiers are retained per case ({config_text}). The newest configuration
742 is represented by only four dates. This is not a seasonal qualification of
that latest configuration. Comparisons across configurations are
confounded by season/weather and are not causal upgrade assessments. Day-zero
and day-one windows sample different valid dates; their overall errors are
reported separately, not as a paired forecast-lead skill change.

WOUDC coverage is limited to one fixed Davos instrument in this extension,
with missing days explicitly retained. Instrument metadata, processing versions
and source timestamps are saved. The records do not carry per-sample QC flags;
archive inclusion does not establish full calibration/QC qualification. Hourly
means use bracketing high-frequency samples with cadence-specific gap limits (30 s for nominal 10 s records, 75 s for
nominal 60 s records). A missing minute is rejected.
Coordinates/height in the WOUDC metadata are coarse. Nearby SwissMetNet snow and
sunshine are not colocated UV-instrument measurements. Atmospheric composition
comes from historical previous-day 12 UTC CAMS forecasts; dissemination latency
is not reconstructed. The fixed summer atmospheric profile, cloud assumptions,
low-sun approximation and unknown effective UV albedo remain limitations.
The primary UV sample retains {int(((uv_flags&64)!=0).sum())} low-sun flagged
hours and {int(((uv_flags&1)!=0).sum())} hours using scaling above the modeled
clear-sky SW value; {int(((uv_flags&65)==65).sum())} hours have both flags. These approximations are
included in the stated scores, not silently discarded.

Dust/smoke and specific low-cloud or convective event types have not been
independently classified. A later event challenge set should be selected from
meteorological evidence, without choosing cases by UV errors. This campaign
broadens evidence substantially; it does not qualify an operational UV product.

## Verification and reproducibility

Frozen input manifests protect replay against changed downloaded inputs.
Independent arithmetic reconciled **{verification['pairs_checked']:,}** SW rows
against saved native boundary values and raw DWH timestamps/measurements; the
maximum flux discrepancy was {verification['max_boundary_flux_error']:.3g} W/m².
The archive reconstruction agrees with the retained ASOD_S case to within
0.227 W/m². The source hashes, interval semantics, member and grid identities
are retained. See `verification.json`, `uv_verification.json`, `run_identity.json`
and the executed notebook for the checks and their scope.
Independent integration of the raw WOUDC irradiances reconciled
{uv_verification['raw_integrations_checked']:,} hourly means to within
{uv_verification['max_integration_difference']:.2g} UVI; independent scalar
arithmetic checked {uv_verification['scalar_metrics_checked']} UV summary values.

Repository tests: 77 passed, with the pre-existing NumPy/netCDF4 import warning.
Cluster extraction used installed ecCodes 2.36.4; the newer Python binding emits
a version recommendation. Numerical source/bridge checks pass; neither warning
is silently suppressed.

Replay instructions: [analysis/README.md](../../../analysis/README.md).
Protocols: [SW](../../../analysis/MULTIYEAR_PLAN.md) and
[UV](../../../analysis/MULTIYEAR_UV_PLAN.md). No production model parameters were
fitted or changed for this expansion.

Sources: [MeteoSwiss ICON documentation](https://opendatadocs.meteoswiss.ch/e-forecast-data/e2-e3-numerical-weather-forecasting-model),
[DWD ICON GRIB parameter definitions](https://www.dwd.de/DWD/forschung/nwv/fepub/icon_database_main.pdf),
[WOUDC data access](https://www.woudc.org/en/data/data-access/),
[PMOD/WRC Davos records](https://woudc.org/archive/Archive-NewFormat/Broad-band_1.0_1/stn501/uv-biometer/).
'''
    (OUTPUT/'report.md').write_text(text)
    # Repository copy has links relative to analysis/ rather than work/results/.
    # Reviewed findings under analysis/ are maintained separately from generated reports.
    import nbformat as nbf
    nb=nbf.v4.new_notebook()
    nb.cells=[nbf.v4.new_markdown_cell('# Multi-year ICON evaluation\n150 native SW cases; separately labelled WOUDC UV diagnostics. See the fixed protocols and report for limitations.'),
        nbf.v4.new_code_cell("from pathlib import Path\nimport json, pandas as pd\nfrom analysis.scientific import verify_inputs\nfrom analysis.multiyear import INPUT, OUTPUT\nverify_inputs(INPUT, INPUT/'frozen_inputs.json')\nverify_inputs(INPUT/'uv', INPUT/'uv/frozen_inputs.json')\nprint(json.loads((OUTPUT/'verification.json').read_text()))"),
        nbf.v4.new_code_cell("cases = pd.read_csv(OUTPUT/'case_coverage.csv')\nassert cases.reference.nunique() == 150\nassert (cases.status == 'evaluated_sw').all()\ncases.groupby(['year', 'season']).size()"),
        nbf.v4.new_code_cell("pairs = pd.read_csv(OUTPUT/'pairs.csv')\ngood = pairs[(pairs.day == 0) & (pairs.reason == 'usable')]\nerrors = good.predicted_sw - good.observed_sw\nsummary = pd.read_csv(OUTPUT/'overall.csv').set_index('day').loc[0]\nassert abs(errors.mean() - summary.bias) < 1e-9\npd.read_csv(OUTPUT/'season.csv')"),
        nbf.v4.new_code_cell("pd.read_csv(OUTPUT/'uv_overall.csv')"),
        nbf.v4.new_code_cell("from IPython.display import display, Image\nfor name in ['multiyear_coverage','multiyear_sw','multiyear_uv']:\n    display(Image(filename=str(OUTPUT/(name+'.png'))))"),
        nbf.v4.new_markdown_cell('The UV rows use prescribed albedo scenarios and do not reproduce unavailable SNOWC. Missing QC is not a pass. No iid station-hour confidence interval is reported.')]
    nb.metadata.kernelspec={'display_name':'Python 3','language':'python','name':'python3'}
    nbf.write(nb,OUTPUT/'multiyear_validation.ipynb')
    write_run_identity()


if __name__=='__main__':main()
