"""Publication figures from independently checked callback-cost joins."""
from refresh import *
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import LogLocator, NullFormatter, MaxNLocator, FixedLocator, FuncFormatter
from matplotlib.colors import LogNorm

ORDER=['dsda','rbfopt','bam','fmqa_sa']
COLORS=dict(zip(ORDER,['#1f77b4','#e1812c','#319754','#9467bd']))
LABEL=dict(zip(ORDER,['DSDA','RBFOpt','BAM','FMQA-SA']))
LS=dict(zip(ORDER,['-','--','-.',':']));MK=dict(zip(ORDER,['o','s','^','D']))
PANELS=[('column',16),('cstr_30',43),('small_batch',10)]+[('dynamic',b) for b in [12,15,20,30,37,50]]
DEST=OUT/'figures'; DEST.mkdir(parents=True,exist_ok=True)

def name(c,b):return c.replace('cstr_','CSTR ').replace('small_batch','Small Batch').replace('column','Column').replace('dynamic','Dynamic')+f' (B={b})'
def grid():
    fig,axs=plt.subplots(3,3,figsize=(7.5,6.4))
    for ax,(c,b) in zip(axs.flat,PANELS):
        ax.set_title(name(c,b),pad=5);ax.grid(alpha=.28);ax.set_axisbelow(True)
    return fig,list(axs.flat)
def legend(fig):
    fig.legend(handles=[Line2D([],[],color=COLORS[m],ls=LS[m],marker=MK[m],ms=3,lw=1.3,label=LABEL[m]) for m in ORDER],loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,.005),columnspacing=1.5)
def logticks(axis,lo,hi):
    vs=[f*10.0**k for k in range(math.floor(math.log10(lo))-1,math.ceil(math.log10(hi))+1) for f in (1,2,5) if lo<=f*10.0**k<=hi]
    if len(vs)<2:vs=list(np.geomspace(lo*1.03,hi/1.03,3))
    if len(vs)>4:vs=vs[::math.ceil(len(vs)/4)]
    axis.set_major_locator(FixedLocator(vs));axis.set_major_formatter(FuncFormatter(lambda v,p:f'{v:.3g}'))
    axis.set_minor_formatter(NullFormatter())
def save(fig,n,rect=(.01,.065,.995,.995)):
    fig.tight_layout(rect=rect,h_pad=1.8,w_pad=1.6)
    for ext in ['pdf','png']:
        fig.savefig(DEST/f'{n}.{ext}',dpi=200,bbox_inches='tight',pad_inches=.04)
    plt.close(fig)

def build(runs,sums):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,'axes.labelsize':8,
        'xtick.labelsize':7.5,'ytick.labelsize':7.5,'legend.fontsize':8,'axes.spines.top':False,
        'axes.spines.right':False,'pdf.fonttype':42,'axes.linewidth':.65,'grid.linewidth':.5})
    gr=a.group_runs(runs);sg=a.group_lookup(sums)
    fig,axs=grid()
    for ax,(c,b) in zip(axs,PANELS):
        for m in ORDER:
            rr=gr[c,b,m];xs=np.arange(1,b+1)
            ys=[sum(r['category']=='target_reached' and r['first_hit_callback']<=i for r in rr)/10 for i in xs]
            marks=sorted(set([*range(0,b,max(1,b//5)),b-1]))
            ax.step(xs,ys,where='post',color=COLORS[m],ls=LS[m],lw=1.3,marker=MK[m],ms=2.7,markevery=marks)
        ax.axvline(3,color='#999999',lw=.6,ls=':')
        ax.set(xlim=(.7,b+.025*b),ylim=(-.03,1.05),yticks=[0,.5,1],xlabel='Charged evaluations',ylabel='Target-hit fraction')
        ax.set_xticks(sorted(set([1,round(b/3),round(2*b/3),b])))
    legend(fig);save(fig,'process_evaluation_profiles')
    fig,axs=grid()
    for ax,(c,b) in zip(axs,PANELS):
        vals=[r['reconstructed_total_s'] for m in ORDER for r in gr[c,b,m] if a.finite(r['reconstructed_total_s'])]
        left,right=min(vals)*.8,max(vals)*1.25
        for m in ORDER:
            successes=[r['reconstructed_total_s'] for r in gr[c,b,m] if r['category']=='target_reached']
            assert all(a.finite(t) for t in successes)
            xs=sorted({left,right,*successes});ys=[sum(v<=x for v in successes)/10 for x in xs]
            ax.step(xs,ys,where='post',color=COLORS[m],ls=LS[m],lw=1.3,marker=MK[m],ms=2.7,markevery=max(1,len(xs)//5))
        ax.set(xscale='log',xlim=(left,right),ylim=(-.03,1.05),yticks=[0,.5,1],xlabel='Completion estimate (s)',ylabel='Target-hit fraction')
        logticks(ax.xaxis,left,right)
    legend(fig);save(fig,'process_completion_profiles')
    fig,axs=grid()
    for ax,(c,b) in zip(axs,PANELS):
        vals=[]
        for j,m in enumerate(ORDER):
            rr=gr[c,b,m];good=[r for r in rr if a.finite(r['reconstructed_total_s'])];vs=[r['reconstructed_total_s'] for r in good];vals+=vs
            for r in good:
                marker='o' if r['category']=='target_reached' else 'X' if r['category']=='execution_failed' else 'x'
                ax.scatter(j+(r['seed']-4.5)*.048,r['reconstructed_total_s'],color=COLORS[m],marker=marker,s=15,linewidths=.8,zorder=4)
            if len(good)==10:ax.hlines(statistics.median(vs),j-.3,j+.3,color='#202020',lw=1)
            if len(good)<10:ax.text(j,.97,f'{len(good)}/10',transform=ax.get_xaxis_transform(),ha='center',va='top',fontsize=7,color='#555555')
        ax.set(yscale='log',ylim=(min(vals)*.65,max(vals)*1.65),xticks=range(4),xticklabels=['D','R','B','F'],ylabel='Completion estimate (s)')
        logticks(ax.yaxis,min(vals)*.65,max(vals)*1.65)
    fig.legend(handles=[Line2D([],[],ls='',marker=z,color='#555555',ms=4,label=t) for z,t in [('o','Target hit'),('x','Target miss'),('X','Execution failure')]],loc='lower center',ncol=3,frameon=False,bbox_to_anchor=(.5,.005))
    save(fig,'process_completion_scatter')
    fig,axs=plt.subplots(2,2,figsize=(7.5,4.9))
    components=[('#5086ad','///','Search overhead'),('#c2c7cc','','Point evaluations'),('#b58fc4','xx','Dynamic preparation')]
    for ax,(c,b) in zip(axs.flat,[('column',16),('cstr_30',43),('small_batch',10),('dynamic',50)]):
        for j,m in enumerate(ORDER):
            rr=gr[c,b,m]
            if not all(a.finite(r['reconstructed_total_s']) for r in rr):
                ax.text(j,50,'N/A',ha='center',color='#555555');continue
            v=[statistics.mean(r['dfo_wall_s']-r['lookup_wall_s'] for r in rr),statistics.mean(r['historical_nlp_known_within_budget_s'] for r in rr),statistics.mean(r['dynamic_preparation_s'] for r in rr)]
            total=sum(v);bt=0
            for vv,(color,hatch,label) in zip(v,components):
                pc=100*vv/total
                ax.bar(j,pc,bottom=bt,color=color,hatch=hatch,edgecolor='#444444',linewidth=.4,width=.66)
                if pc>=5:ax.text(j,bt+pc/2,f'{pc:.1f}%',ha='center',va='center',fontsize=7.5)
                bt+=pc
            ax.text(j,102,f'{total:.2f} s',ha='center',va='bottom',fontsize=7.5)
        ax.set(title=name(c,b),xticks=range(4),xticklabels=[LABEL[m] for m in ORDER],ylim=(0,114),yticks=[0,25,50,75,100],ylabel='Share of mean total (%)')
        ax.grid(axis='y',alpha=.25);ax.set_axisbelow(True)
    fig.legend(handles=[Patch(facecolor=c,hatch=h,edgecolor='#444444',label=l) for c,h,l in components],loc='lower center',ncol=3,frameon=False,bbox_to_anchor=(.5,.002))
    save(fig,'process_cost_breakdown',rect=(.01,.075,.995,.995))
    for field,fn in [('hits','process_targets'),('tts99_s','process_tts99_all_conditions')]:
        fig,ax=plt.subplots(figsize=(6.3,6.4))
        arr=np.array([[sg[c,b,m][field] if a.finite(sg[c,b,m][field]) else np.nan for m in ORDER] for c,b in a.CONDITIONS])
        opts={'vmin':0,'vmax':10,'cmap':'Blues'} if field=='hits' else {'norm':LogNorm(vmin=np.nanmin(arr),vmax=np.nanmax(arr)),'cmap':'viridis'}
        ax.imshow(np.ma.masked_invalid(arr),aspect='auto',**opts)
        ax.set(xticks=range(4),xticklabels=[LABEL[m] for m in ORDER],yticks=range(14),yticklabels=[name(c,b) for c,b in a.CONDITIONS])
        for i,(c,b) in enumerate(a.CONDITIONS):
            for j,m in enumerate(ORDER):
                v=sg[c,b,m][field];s=f'{v}/10' if field=='hits' else f'{v:.2f}' if a.finite(v) else 'inf' if v is not None else 'N/A'
                white=(v>=7 if field=='hits' else a.finite(v) and v<500)
                ax.text(j,i,s,ha='center',va='center',color='white' if white else '#222222',fontsize=9)
        ax.set_title('Audited target attainment' if field=='hits' else 'Empirical TTS99 (seconds)',pad=10)
        save(fig,fn,rect=(0,0,1,1))
    a.savejson(OUT/'figure_manifest.json',{'panels':PANELS,'four_active_figures':True,'diagnostic_figures':2,
        'completion_profile_denominator':10,'execution_failure_policy':'Contributes zero success; known successful completion times suffice for the profile. No ten-run median or TTS99 for protocol-invalid groups.',
        'files':{p.name:a.sha(p) for p in DEST.glob('*.pdf')}})

if __name__=='__main__':
    runs,events,inputs,costs,sums,summary=load();build(runs,sums)
    print('Created six PDF figures and PNG previews in',DEST)
