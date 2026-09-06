"""Produce a product-focused scorecard with explicit qualification limits."""
import hashlib
import importlib.metadata
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.product_analysis import ROOT,INPUT,OLD,OUTPUT,sha


def main():
    pairs=pd.read_csv(OUTPUT/'daily_pairs.csv');scores=pd.read_csv(OUTPUT/'scores.csv')
    overall=scores[scores.stratum=='day/product'].set_index(['day','product'])
    verification=json.loads((OUTPUT/'verification.json').read_text())
    confidence=json.loads((OUTPUT/'confidence.json').read_text())
    comparisons=json.loads((OUTPUT/'paired_comparisons.json').read_text())
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    colors=['#28638a','#b96934','#4e886e']
    for i,(product,label) in enumerate([('native','Native SW'),('gray','Gray baseline'),('measured_sw','Measured SW experiment')]):
        rows=[overall.loc[(d,product)] for d in (0,1)]
        for ax,metric in zip(axes,['within_one','same_category']):
            x=np.arange(2)+(i-1)*.24
            values=np.array([r[metric]*100 for r in rows])
            intervals=np.array([next(c['intervals'][metric] for c in confidence if c['block']==3 and c['day']==d and c['product']==product) for d in (0,1)])*100
            ax.bar(x,values,.24,color=colors[i],label=label)
            ax.errorbar(x,values,yerr=np.maximum(0,np.vstack([values-intervals[:,0],intervals[:,1]-values])),fmt='none',color='#222',capsize=3,linewidth=1)
    for ax,target,title in zip(axes,[90,80],['Within one displayed UVI unit','Exact category agreement']):
        ax.axhline(target,color='#333',linestyle='--',linewidth=1,label=f'Working target {target}%')
        ax.set(xticks=[0,1],xticklabels=['Initialization day','Following day'],ylim=(0,105),ylabel='Paired site-days (%)',title=title)
        ax.spines[['top','right']].set_visible(False)
    axes[0].legend(loc='upper center',bbox_to_anchor=(.5,-.13),fontsize=8,frameon=False,ncol=2)
    fig.suptitle('Davos daily peaks: retrospective diagnostics with 95% date-block intervals')
    for suffix in ['png','pdf']:fig.savefig(OUTPUT/f'product_scores.{suffix}',dpi=170,bbox_inches='tight')
    plt.close(fig)
    table='| Day | Method | Dates | MAE (UVI) | Within 1 displayed unit | Same category |\n|---|---|---:|---:|---:|---:|\n'
    for day in (0,1):
        for product,label in [('native','Native SW'),('gray','Gray baseline'),('measured_sw','Measured-SW attribution')]:
            r=overall.loc[(day,product)]
            table+=f'| {day} | {label} | {int(r.usable)} | {r.mae:.3f} | {r.within_one:.1%} | {r.same_category:.1%} |\n'
    bounds=[]
    for c in confidence:
        if c['block']==3 and c['product']=='native':
            a,b=c['intervals']['within_one'];x,y=c['intervals']['same_category']
            bounds.append(f"Day {c['day']}: within-one 95% interval {a:.1%}–{b:.1%}; category agreement {x:.1%}–{y:.1%}.")
    delta=next(r for r in comparisons if r['day']==0 and r['block']==3 and r['left']=='native' and r['right']=='measured_sw')
    native=overall.loc[(0,'native')]
    date_pairs=pairs[(pairs['product']=='native')&(pairs.reason=='usable')]
    temporal=[]
    for day,g in date_pairs.groupby('day'):
        d=g.observed_uvi-g.observed_hourly_max
        count=int(np.sum(np.floor(g.observed_uvi+.5)!=np.floor(g.observed_hourly_max+.5)))
        temporal.append(f'Day {day}: {count}/{len(g)} displayed integers change; median peak difference {d.median():.3f}, 90th percentile {d.quantile(.9):.3f} UVI.')
    text=f'''# Product readiness: first verified milestone

**A functioning daily map-data export is available. Broad scientific qualification
is not established, and the current historical diagnostic does not meet all
working accuracy targets. The goal remains active.**

## Product-level evidence

{table}
Day 0/1 are separate valid dates, not paired lead-time degradation estimates.
All entries above use one fixed Davos UV instrument, full-day observation
coverage, prescribed UV albedo 0.05 and reconstructed 30-minute peaks.

![Product scorecard](product_scores.png)

The native method has a modest paired daily-MAE advantage over the gray baseline
on these data. This is a different metric from the earlier hourly comparison.
Substituting nearby measured SW reduces native MAE by {delta['delta_mae_left_minus_right']:.3f}
UVI (paired seasonal block-bootstrap 95% interval
{delta['ci95'][0]:.3f}–{delta['ci95'][1]:.3f}). This identifies shortwave input
error as a useful development priority, but the substitution is not a forecast
and the two observing locations are not identical.

{' '.join(bounds)} The 90% within-one and 80% category targets are therefore not
established by their lower uncertainty bounds. Summer initialization-day category
agreement is only 60% on 20 dates; pooled winter accuracy is not sufficient.

No two-category underestimates occur among the 66 primary dates; one occurs
among 65 following-day dates. A zero-event empirical bootstrap gives [0,0],
which cannot bound the probability of an unseen event and is not a reliability
guarantee. There are no observed extreme-category days and only 12/14 very-high
days. Primary native forecasts miss the observed >=8 category on 6/12 dates.
Rare-category and geographical coverage remain insufficient for qualification.

## Temporal resolution matters at display precision

{' '.join(temporal)} These differences compare raw observed 30-minute and
clock-hour maxima; the reconstructed model cannot resolve actual subhourly cloud
evolution. The contract keeps that limitation explicit. Daily aggregation must
not silently use a partial 08–16 UTC sample.

## Complete-input product demonstration

The retained recent example uses 1781 native cells, actual ICON SNOWC and 12
solar samples per hour. It produces 54 entries: 12 towns/vicinities and five
illustrative mountain regions at 1000/2000/3000 m, for two days. All entries have
complete required daylight/support in this example. Regions use native terrain
cells near each altitude, not a vertically shifted valley cloud column.

The grid calculation took about 13.5 s on this Mac, excluding data retrieval,
export and startup; this is a measured example, not an operational latency SLA.
The example's issuance is fixed for replay and does not prove historical input
delivery time. Catalog coordinates/boxes are explicitly illustrative. Structural
`ok` status means input-contract checks passed, not validated forecast skill.

[Interface and replay instructions](../../../analysis/PRODUCT_DATA_INTERFACE.md)
and [example JSON](../product-example.json).

## Verification

All 150 new native cases and 300 DWH windows are retained separately from the
prior campaign. All eight Slurm tasks completed successfully. The independent
bridge reconciled {verification['unchanged_native_boundary_values']:,} original
native boundary values exactly. Independently interpolating raw UV measurements
to a one-second grid and integrating checked {verification['observed_daily_maxima']}
daily maxima, maximum difference {verification['maximum_peak_difference']:.2g}
UVI. Independent scalar arithmetic checked {verification['independent_summary_values']}
summary values. Repository tests: 98 passed, with the pre-existing netCDF4 import
warning. Frozen inputs, source identities and all date-level exclusions are saved.

## Remaining work toward the active goal

1. Add independent, quality-controlled UV observations at more sites/elevations,
   including snow and high/extreme UV; reserve fresh evaluation data before tuning.
2. Investigate cloud/SW and temporal-peak behavior using the new attribution
   result. Evaluate candidate changes against display/category outcomes, with
   independent data and explicit rare-event uncertainty.
3. Perform targeted snow/albedo, seasonal-profile and high-elevation reference
   checks. The prescribed-surface historic score cannot qualify production snow
   treatment or the illustrative regional percentile product.
4. Validate the current ICON configuration separately, finish geographic
   acceptance and delivery-latency requirements, and expand interface/schema
   and failure-mode checks where those requirements reveal gaps.

The existing 2024–2025 UV data do not validate the newest ICON configuration or
all regions shown by the example. No public deployment or automated collection
has been started.
'''
    (OUTPUT/'report.md').write_text(text)
    # Reviewed findings under analysis/ are maintained separately from generated reports.
    files=sorted((ROOT/'icon_uv').glob('*.py'))+sorted((ROOT/'analysis').glob('product*.py'))+[ROOT/'analysis/report_product.py',ROOT/'analysis/verify_product_analysis.py']
    identity=dict(code={str(p.relative_to(ROOT)):sha(p) for p in files},
                  packages={name:importlib.metadata.version(name) for name in ['numpy','scipy','pandas','xarray','matplotlib']},
                  input_manifest_sha256=sha(INPUT/'frozen_inputs.json'),example_identity_sha256=sha(INPUT/'example_identity.json'),
                  results={p.name:sha(p) for p in sorted(OUTPUT.glob('*.csv'))},checks=verification,
                  scope='retrospective single-instrument prescribed-albedo diagnostics; complete-input example is separate')
    (OUTPUT/'run_identity.json').write_text(json.dumps(identity,indent=2))
    assessment=dict(qualification='not_established',goal_status='active',
                    sample_scope='one historical UV instrument; prescribed albedo; no observed extreme-category dates',
                    caveats=['Empirical zero-event bootstrap intervals cannot bound unseen-event risk.',
                             'Recent complete-input export is an implementation demonstration, not skill validation.',
                             'Region catalog and aggregation are illustrative; current configuration lacks seasonal UV evidence.'],
                    days=[])
    for day in (0,1):
        r=overall.loc[(day,'native')]
        c=next(x for x in confidence if x['day']==day and x['product']=='native' and x['block']==3)
        assessment['days'].append(dict(day=day,paired_dates=int(r.usable),
            point_target_meets=dict(within_one=bool(r.within_one>=.9),same_category=bool(r.same_category>=.8),under_two_categories=bool(r.under_two_categories<.05)),
            accuracy_lower_bound_meets=dict(within_one=c['intervals']['within_one'][0]>=.9,same_category=c['intervals']['same_category'][0]>=.8),
            rare_event_target='insufficient coverage; empirical interval alone is not a qualification'))
    (OUTPUT/'assessment.json').write_text(json.dumps(assessment,indent=2))


if __name__=='__main__':main()
