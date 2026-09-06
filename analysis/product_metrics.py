"""Product-level scores and paired seasonal date-block uncertainty."""
import numpy as np


def product_scores(observed, predicted):
    observed, predicted = np.broadcast_arrays(np.asarray(observed,float),np.asarray(predicted,float))
    if not observed.size or not np.isfinite(observed+predicted).all() or np.any(np.minimum(observed,predicted)<0):
        raise ValueError('Nonempty, finite nonnegative paired UVI required')
    oi=np.floor(observed+.5).astype(int);pi=np.floor(predicted+.5).astype(int)
    oc=np.searchsorted([3,6,8,11],oi,side='right');pc=np.searchsorted([3,6,8,11],pi,side='right')
    error=predicted-observed
    result=dict(n=len(observed),bias=float(error.mean()),mae=float(abs(error).mean()),
                absolute_error_p90=float(np.quantile(abs(error),.9)),
                within_one=float(np.mean(abs(pi-oi)<=1)),same_category=float(np.mean(oc==pc)),
                under_two_categories=float(np.mean(oc-pc>=2)))
    for threshold in [3,6,8,11]:
        mask=oi>=threshold;raw=observed>=threshold
        result[f'observed_ge_{threshold}']=int(mask.sum())
        result[f'miss_ge_{threshold}']=float(np.mean(pi[mask]<threshold)) if mask.any() else None
        result[f'raw_observed_ge_{threshold}']=int(raw.sum())
        result[f'raw_miss_ge_{threshold}']=float(np.mean(predicted[raw]<threshold)) if raw.any() else None
    high=oi>=8
    result['observed_very_high']=int(high.sum())
    result['very_high_forecast_below_high']=float(np.mean(pi[high]<6)) if high.any() else None
    return result


def date_block_indices(dates, seasons, *, block=3, repeats=2000, seed=20260906):
    """Keep every site's rows in a date together; stratify circular blocks by season."""
    dates=np.asarray(dates);seasons=np.asarray(seasons)
    if len(dates)!=len(seasons) or not len(dates) or block<1 or repeats<1:
        raise ValueError('Invalid date bootstrap inputs')
    unique=np.unique(dates)
    labels={d:np.unique(seasons[dates==d]) for d in unique}
    if any(len(v)!=1 for v in labels.values()):raise ValueError('A date has inconsistent seasons')
    groups=[np.array([d for d in unique if labels[d][0]==s]) for s in np.unique(seasons)]
    members={d:np.flatnonzero(dates==d) for d in unique}
    rng=np.random.default_rng(seed)
    for _ in range(repeats):
        selected=[]
        for group in groups:
            starts=rng.integers(0,len(group),size=int(np.ceil(len(group)/block)))
            selected.extend(group[(starts[:,None]+np.arange(block))%len(group)].ravel()[:len(group)])
        yield np.concatenate([members[d] for d in selected])


def score_intervals(frame, *, block=3, repeats=2000):
    keys=('within_one','same_category','under_two_categories','bias','mae')
    scores=[]
    observed=frame.observed_uvi.to_numpy();predicted=frame.predicted_uvi.to_numpy()
    for idx in date_block_indices(frame.valid_date,frame.season,block=block,repeats=repeats):
        s=product_scores(observed[idx],predicted[idx]);scores.append([s[k] for k in keys])
    quantiles=np.quantile(scores,[.025,.975],axis=0)
    return {k:[float(quantiles[0,i]),float(quantiles[1,i])] for i,k in enumerate(keys)}
