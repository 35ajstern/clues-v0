from __future__ import division
from itertools import product
import numpy as np
from scipy.misc import logsumexp
import scipy.stats as stats
import clues_utils
import glob
import h5py
from Bio import Phylo
from io import StringIO
import warnings
import argparse

warnings.filterwarnings("ignore")

parser = argparse.ArgumentParser(description=
                'CLUES calculates an estimate of the log-likelihood ratio of '+
                'selection along a grid of sites (fixed derived and/or segregating)'+
                'across a set of homologous sequences.')
# mandatory inputs:
parser.add_argument('treesFile',type=str,help='A file of local trees at the site of interest. Extract these using arg-summarize (a tool in ARGweaver)')
parser.add_argument('conditionalTrans',type=str,help='an .hdf5 file that specifies the conditional transition probabilities and stationary frequency distn, as well as metadata') 
parser.add_argument('sitesFile',type=str,help='The data file used as input to sample ARGs in ARGweaver (.sites format)')
parser.add_argument('popFreq',type=float,help='Population frequency of the SNP of interest.')
#parser.add_argument('logFile',type=str,help='The .log file generated by arg-sample; we use this to find out the time-discretization and popsize model used during ARG sampling.') 
#parser.add_argument('transMatsDir',type=str,help='A folder containing .h5 files that contain transition probabilities + metadata for a set of discrete timesteps. Each .h5 file corresponds to a value of s')

# options:
parser.add_argument('-timeScale','--timeScale',type=float,help='Multiply the coal times in bedFile by this factor to get in terms of generations; e.g. use this on trees in units of 4N gens (--timeScale <4*N>)',default=1)
parser.add_argument('-q','--quiet',action='store_true')
parser.add_argument('-o','--output',dest='outFile',type=str,default=None)

#            type = str, default = (None,None))
parser.add_argument('-posn','--posn',type=int,help='posn of the site of interest; only necessary for segsites.',default=50000)
parser.add_argument('-sitesFile','--sitesFile',type=str,help='.sites file used for arg-sampling; we use this to extract which individuals carry the derived type at the site of interest',default=None)
parser.add_argument('-derivedAllele','--derivedAllele',type=str,help='specifies which allele you assume to be the derived type.',default='G')
parser.add_argument('-ancientHap','--ancientHap',type=str,help='specifies the label of the ancient haplotype that you may include in the .sites file',default='0')
parser.add_argument('-noAncientHap','--noAncientHap',action='store_true')
parser.add_argument('--argweaver',action='store_true')
parser.add_argument('-debug','--debug',action='store_true')
parser.add_argument('-popFreq','--popFreq',type=float,default=None)
parser.add_argument('-thin','--thin',type=int,default=5)
parser.add_argument('--burnin',type=int,default=0)
parser.add_argument('-ssv','--ssv',action='store_true',help='Expands to test for sweeps from a standing variants (SSVs) and outputs estimates of t_s, f_s -- the time and frequency at which selection begins to act on the allele')
parser.add_argument('--idxSel',type=int,default=1)
parser.add_argument('--selCoeff',type=float,default=None)
parser.add_argument('--tSel',type=float,default=None)
parser.add_argument('-prune','--prune',type=str,default=None,help='file that specifies the leaf nodes you wish to prune (ignore) from the genealogies')
parser.add_argument('--invar',action='store_true')
parser.add_argument('--statDistn',action='store_true')
parser.add_argument('--prior',action='store_true',help='uniform prior on sel coeff (and start of SSV if --ssv used)')
parser.add_argument('--approx',type=float,help='the generation after which (bkwds in time) we will use Tavares exact formula, rather than the Griffiths approx.',default=500)
###############################

args = parser.parse_args()

bedFile = args.treesFile
conditionalTransMats = args.conditionalTrans
#logFile = args.logFile
#transMatDir = args.transMatsDir
outFile = args.outFile
#popsizeFile = args.popsize[0]
#popsizeTransMatDir = args.popsize[1]

def get_branches_all_classes(derTree,ancTree,mixTree,derInds,ancInds,ancHap,n,m,sitesFile):
	
	global SCALED_GENS
	SCALED_GENS = [0]
	#for (i,dt,t) in zip(range(len(AW_TIMES[1:])),np.diff(AW_TIMES),AW_TIMES[1:]):
	#	 SCALED_GENS += [SCALED_GENS[-1] + SAMPLING_POPSIZE[i]/SAMPLING_POPSIZE[0]*dt]

	SCALED_GENS = AW_TIMES
	SCALED_GENS = np.array(SCALED_GENS)
	indsToPrune = []
	if args.prune != None:
		for line in open(args.prune,'r'):
			indsToPrune += [line.rstrip()+'_1',line.rstrip()+'_2']
	if sitesFile == None:
		### assume all individuals are fixed for the derived type!
		if ancHap != None:
			raise NotImplementedError
		else:
			derTimes = args.timeScale * np.sort(clues_utils.coal_times(derTree.clade.clades))	
			ancTimes = args.timeScale *np.sort(clues_utils.coal_times(ancTree.clade.clades))
			mixTimes = args.timeScale *np.sort(clues_utils.coal_times(mixTree.clade.clades))
			Cder = clues_utils.branch_counts(derTimes,SCALED_GENS,eps=10**-10)[1:] + [1]
			Canc = clues_utils.branch_counts(ancTimes,SCALED_GENS,eps=10**-10)[1:] + [1]
			Cmix = clues_utils.branch_counts(mixTimes,SCALED_GENS,eps=10**-10)[1:] + [1]

	if ancHap == None:
		ancHap = []
	if n >= 2 and m >= 2:	
		for ind in set(ancInds + ancHap + indsToPrune):
			#print(ind)
			derTree.prune(ind)
		for ind in set(derInds + ancHap + indsToPrune):
			ancTree.prune(ind)
		for ind in set(derInds[1:] + ancHap + indsToPrune):
			mixTree.prune(ind)
	
		derTimes = args.timeScale * np.sort(clues_utils.coal_times(derTree.clade.clades))	
		print(derTimes)
		ancTimes = args.timeScale *np.sort(clues_utils.coal_times(ancTree.clade.clades))
		mixTimes = args.timeScale *np.sort(clues_utils.coal_times(mixTree.clade.clades))
		Cder = clues_utils.branch_counts(derTimes,SCALED_GENS,eps=10**-10)[1:] + [1]
		Canc = clues_utils.branch_counts(ancTimes,SCALED_GENS,eps=10**-10)[1:] + [1]
		Cmix = clues_utils.branch_counts(mixTimes,SCALED_GENS,eps=10**-10)[1:] + [1]
		#print(Canc,Cmix)

	elif n == 1 and m >= 2:
		for ind in set(derInds + ancHap + indsToPrune):
			ancTree.prune(ind)
		for ind in set(derInds[1:] + ancHap + indsToPrune):
			mixTree.prune(ind)
	
		ancTimes = args.timeScale * np.sort(clues_utils.coal_times(ancTree.clade.clades))
		mixTimes = args.timeScale * np.sort(clues_utils.coal_times(mixTree.clade.clades))
		#print(n,m)
		Cder = [1]
		Canc = clues_utils.branch_counts(ancTimes,SCALED_GENS,eps=0.001)[1:] + [1]
		Cmix = clues_utils.branch_counts(mixTimes,SCALED_GENS,eps=0.0011)[1:] + [1]
		#print(Canc,Cmix)
	
	elif n >= 2 and m == 1:
		for ind in set(ancInds + ancHap + indsToPrune):
			derTree.prune(ind)
		for ind in set(derInds[1:] + ancHap + indsToPrune):
			mixTree.prune(ind)
	
		derTimes = args.timeScale * np.sort(clues_utils.coal_times(derTree.clade.clades))	
		mixTimes = args.timeScale * np.sort(clues_utils.coal_times(mixTree.clade.clades))
		#print(n,m)
		Cder = clues_utils.branch_counts(derTimes,SCALED_GENS,eps=1)[1:] + [1]
		Canc = [1]
		Cmix = clues_utils.branch_counts(mixTimes,SCALED_GENS,eps=1)[1:] + [1]
	elif n == 0 and m >= 2:
		Cder = [0]
		for ind in set(ancHap + indsToPrune):
			ancTree.prune(ind)
		ancTimes = args.timeScale * np.sort(clues_utils.coal_times(ancTree.clade.clades))
		Canc = clues_utils.branch_counts(ancTimes,SCALED_GENS,eps=1)[1:] + [1]
		Cmix = Canc

	elif n >= 2 and m == 0:
		Canc = [0]
		for ind in set(ancHap + indsToPrune):
			derTree.prune(ind)
		derTimes = args.timeScale * np.sort(clues_utils.coal_times(derTree.clade.clades))
		Cder = clues_utils.branch_counts(derTimes,SCALED_GENS,eps=1)[1:] + [1]	
		Cmix = [1]
	
	return Cder,Canc,Cmix


def lookup_alpha(i,i_coal,s,i_sel,N,Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,alpha=0,dpfi=None,sampling=False):

	global ALPHA_DICT
	global SAMPLING_TRANS 
	global ds
	localTrans = SAMPLING_TRANS[i_s,ii_sel,i,::] 

	dtcoal = ds[i_coal]	
	
	val = np.array([ lookup_log_tavare_structured(Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,N,FREQS[v],dtcoal,i>GRIFFITHS_TAVARE_CHANGEPOINT) + logsumexp(localTrans[:,v] + alpha ) for v in range(NG)])
	#print(i,[ (lookup_log_tavare_structured(Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,N,FREQS[v],dtcoal) , logsumexp(localTrans[:,v] + alpha )) for v in range(NG)])

	return val

def lookup_beta(i,i_coal,i_s,ii_sel,N,Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,beta=0,dpfi=None,sampling=False):
	global BETA_DICT
	global SAMPLING_TRANS 
	global ds
	global GRIFFITHS_TAVARE_CHANGEPOINT
	localTrans = SAMPLING_TRANS[i_s,ii_sel,i,::] 
		
	dtcoal = ds[i_coal]
		 
	coal_vec = np.array([lookup_log_tavare_structured(Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,N,FREQS[v],dtcoal,i>GRIFFITHS_TAVARE_CHANGEPOINT) for v in range(NG)])
	val = np.array([logsumexp( np.array([localTrans[u,v] + coal_vec[v] for v in range(NG)]) + beta ) for u in range(NG)]) 
	#if args.debug:
		#if -np.inf in [lookup_log_tavare_structured(Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,N,FREQS[v],dtcoal) for v in range(NG)][1:-1]:
		#	print(S_GRID[i_s],i,Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,dtcoal,[lookup_log_tavare_structured(Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,N,FREQS[v],dtcoal) for v in range(NG)])
	#	print(S_GRID[i_s],i,Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,dtcoal,val)
	return val

def lookup_log_tavare_structured(Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,Nnow,x,t,isTavare):
	global LOG_TAVARE_CONDITIONAL_LIKELIHOOD_DICT
	try:
		val = LOG_TAVARE_CONDITIONAL_LIKELIHOOD_DICT[(Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,Nnow,x,t,isTavare)]
	except:
		val = clues_utils.tavare_structured_coal(Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,Nnow,x,t,isTavare)
		LOG_TAVARE_CONDITIONAL_LIKELIHOOD_DICT[(Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,Nnow,x,t,isTavare)] = val
	return val

def backward_algorithm(C,i_s,ii_sel,popsize,n,m,ds,sampling=False,returnBeta=False):
	'''
	Need to add description
	'''
	global TIME_BETA_DICT
	global discretizedPopFreqIdx
	betas = {}
	for i in range(1,len(ds)+1):
		dt = ds[i-1]
		if i == 1:
			localTrans = SAMPLING_TRANS[i_s,ii_sel,0,:,:] 
			beta = localTrans[:,discretizedPopFreqIdx] 
			#import pdb; pdb.set_trace()
			TIME_BETA_DICT[(k,i_s,ii_sel,i)] = beta
			betas[i] = beta
			continue
		elif i == 2:
			Cder0 = n
			Canc0 = m
			if m >= 1 and n >= 1:
				Cmix0 = m+1
			elif m == 0 and n >= 2:
				Cmix0 = 1
			elif m >= 2 and n == 0:
				Cmix0 = m
		else:
			Cder0 = Cder1
			Canc0 = Canc1
			Cmix0 = Cmix1
		Cder1 = C[0][i-1]
		Canc1 = C[1][i-1]
		Cmix1 = C[2][i-1]	
		N = popsize[i-2]
		dtcoal = ds[i-2]
		betaPrev = beta
		beta = lookup_beta(i-1,i-2,i_s,ii_sel,N,Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,beta=beta,dpfi=discretizedPopFreqIdx,sampling=sampling)
 		
		TIME_BETA_DICT[(k,i_s,ii_sel,i)] = beta
		if returnBeta:
			betas[i] = beta
	if returnBeta:
		return betas
	else:
		return beta[0]

def forward_algorithm(C,i_s,ii_sel,popsize,n,m,ds,sampling=False,returnAlpha=False):
	'''
	Need to add description
	'''
	global TIME_ALPHA_DICT
	global discretizedPopFreqIdx
	alphas = {}
	for i in range(len(ds)-1,-1,-1):
		if i == len(ds)-1:
			alpha = -np.inf * np.ones(len(FREQS))
			alpha[0] = 0
			TIME_ALPHA_DICT[(i_s,ii_sel,i+1)] = alpha
			alphas[i+1] = alpha
		if i == 0:
			dt = ds[0]
			localTrans = SAMPLING_TRANS[i_s,ii_sel,i,:,:] 
			alpha = np.array([logsumexp(localTrans[:,v] + alpha) for v in range(NG)]) 
			alphas[0] = alpha
			TIME_ALPHA_DICT[(k,i_s,ii_sel,i)] = alpha
			continue
		elif i == 1:
			Cder0 = n
			Canc0 = m
			if m >= 1 and n >= 1:
				Cmix0 = m+1
			elif m == 0 and n >= 2:
				Cmix0 = 1
			elif m >= 2 and n == 0:
				Cmix0 = m
		else:
			Cder0 = C[0][i-2]
			Canc0 = C[1][i-2]
			Cmix0 = C[2][i-2]
		Cder1 = C[0][i-1]
		Canc1 = C[1][i-1]
		Cmix1 = C[2][i-1]	
		N =  popsize[i-1]
		dtcoal = ds[i-1]
		dt = ds[i]	
		alphaPrev = alpha
		alpha = lookup_alpha(i,i-1,i_s,ii_sel,N,Cder0,Cder1,Canc0,Canc1,Cmix0,Cmix1,alpha=alpha,dpfi=discretizedPopFreqIdx,sampling=sampling)
		TIME_ALPHA_DICT[(k,i_s,ii_sel,i)] = alpha
		if returnAlpha:
			alphas[i] = alpha #- logsumexp(alpha)
	if returnAlpha:
		return alphas
	else:
		return alpha[discretizedPopFreqIdx] 

def write_results_to_h5(args):
	if args.outFile == None:
		return

	global AW_TIMES
	global popsize
	global SAMPLING_POPSIZE
	global FREQS
	global S_GRID
	global iHat
	global jHat
	global tHat
	global sHat
	global xHat
	global I_SEL
	global xHatLo
	global xHatHi
	global xMargs
	global logLikelihoodRatios
	global individualLogLRs


	f = h5py.File(args.outFile+'.h5','w')

	# set attributes
	f.attrs['t'] = AW_TIMES
	f.attrs['popsize'] = popsize
	f.attrs['samplingPopsize'] = SAMPLING_POPSIZE
	f.attrs['freqs'] = FREQS
	f.attrs['sGrid'] = S_GRID
	f.attrs['iHat'] = iHat
	f.attrs['iSel'] = I_SEL
	f.attrs['jHat'] = jHat
	f.attrs['tHat'] = tHat
	f.attrs['sHat'] = sHat
	f.attrs['xHat'] = xHat
	f.attrs['xHatLo'] = xHatLo
	f.attrs['xHatHi'] = xHatHi

	# create_datasets
	f.create_dataset("logLikelihoodRatios", data=logLikelihoodRatios)
	f.create_dataset("logImportanceWeights", data=individualLogLRs)
	f.create_dataset("xMargs", data=np.array(xMargs))
	f.close()

	return

def print_results(args):
	if args.quiet:
		return

	global iHat
	global sHat
	global xHat
	global xHatLo
	global xHatHi
	global xMargs	
	
	global logLikelihoodRatios
	global jHat
	global tHat

	postMed = []
	for b in range(len(ds)):
		marg = stats.rv_discrete(0,1,values=(FREQS,np.exp(xMargs[b])))
		postMed.append(marg.median())
	if not args.invar:
		xHatStr = '['+','.join(['%.4f'%x for x in postMed])+']'
	else:
		xHatStr = '['+','.join(['%.4f'%x for x in xHat])+']'
	xHatLoStr = '['+','.join(['%.4f'%x for x in xHatLo])+']'
	xHatHiStr = '['+','.join(['%.4f'%x for x in xHatHi])+']'

	if args.ssv:
		print('\n'.join([string+' = '+x for (string,x) in zip(['s','lr','x','lo','hi'],[str(sHat),str(logLikelihoodRatios[iHat,jHat]),xHatStr,xHatLoStr,xHatHiStr])]))
		print('SSV lr: %f'%(logLikelihoodRatios[iHat,jHat] - np.max(logLikelihoodRatios[:,-1])))
	else:
		print('\n'.join([string+' = '+x for (string,x) in zip(['s','lr','x','lo','hi'],[str(sHat),str(logLikelihoodRatios[iHat]),xHatStr,xHatLoStr,xHatHiStr])]))
	return

def load_hdf5(reweight=False):
	global SAMPLING_TRANS_h5
	global SAMPLING_POPSIZE 
	global SAMPLING_STAT_DISTN
	global AW_TIMES
	global I_SEL
	global S_GRID
	global FREQS
	global BREAKS
	global BIN_SIZES
	global NG

	samplingTrans  = h5py.File(args.conditionalTrans,'r')
	AW_TIMES = samplingTrans.attrs['t']
	CALC_N = 2000
	SAMPLING_POPSIZE = samplingTrans.attrs['popsize'] 
	SAMPLING_STAT_DISTN = samplingTrans['stat_distn']
	I_SEL = samplingTrans.attrs['iSel']
	S_GRID = samplingTrans.attrs['sGrid']
	FREQS = samplingTrans.attrs['freqs']
	## generate breaks from freqs
	breaks = [0,1/CALC_N]
	for (i,freq) in enumerate(FREQS[1:-2]):
		nextBreak = freq + freq - breaks[i+1]
		breaks.append(nextBreak)
	breaks += [1-1/CALC_N,1]
	BREAKS = np.array(breaks)
	BIN_SIZES = np.diff(breaks[1:-1])	
	NG = len(FREQS)
	SAMPLING_TRANS_h5 = samplingTrans

	return	
## load the arg-sample log to obtain time discretization and sampling popsize
load_hdf5(reweight=False)
popsize = SAMPLING_POPSIZE

ds = np.diff(AW_TIMES)
GRIFFITHS_TAVARE_CHANGEPOINT = np.digitize(args.approx,AW_TIMES)
individualLogLRs = np.zeros(())
## parse the .sites file to get the allelic states at the site of interest
if args.noAncientHap:
	ancientHap = None
else:
	ancientHap = args.ancientHap

indLists = clues_utils.derived_carriers_from_sites(args.sitesFile,
						args.posn,
						derivedAllele=args.derivedAllele,
						ancientHap=ancientHap,
						invar=args.invar)

derInds = indLists[0]
ancInds = indLists[1]
ancHap = indLists[2]

f = open(bedFile,'r')

lines = f.readlines()
lines = [line for line in lines if line[0] != '#' and line[0] != 'R' and line[0] != 'N'][args.burnin::args.thin]
numImportanceSamples = len(lines)

## initialize hash tables
LOG_TAVARE_CONDITIONAL_LIKELIHOOD_DICT = {}
TIME_BETA_DICT = {}
TIME_ALPHA_DICT = {}

idxsSamplesCorrectlyPolarized = [] 
individualMargEsts = []
numSamplesWronglyPolarized = 0
ind_i_hats = []
ind_i_sel_hats = []
branch_lengths = []
individualMargEsts = np.zeros((numImportanceSamples,len(S_GRID),len(I_SEL),len(ds),len(FREQS)))
for (k,line) in enumerate(lines):
	nwk = line.rstrip().split()[-1]
	derTree =  Phylo.read(StringIO(nwk),'newick')
	ancTree = Phylo.read(StringIO(nwk),'newick')
	mixTree = Phylo.read(StringIO(nwk),'newick')
	Phylo.read(StringIO(nwk),'newick')

	n = len(derInds)
	m = len(ancInds)
	if k == 0:
		if args.popFreq != None:
			if args.popFreq != 1:	
				discretizedPopFreqIdx = np.digitize(args.popFreq,FREQS)
				hPlus = FREQS[discretizedPopFreqIdx]-args.popFreq
				hMinus = args.popFreq - FREQS[discretizedPopFreqIdx-1]
				sign = -1*np.random.binomial(1,hPlus/(hPlus+hMinus))
				discretizedPopFreqIdx += sign
			else:
				discretizedPopFreqIdx = len(FREQS)-1
			SAMPLING_TRANS = SAMPLING_TRANS_h5['trans_dpfi%d'%(discretizedPopFreqIdx)]
			if not args.ssv:
				ii_sel_last = len(I_SEL) - 1
				I_SEL = [I_SEL[-1]]
				if args.selCoeff == None:
					I_S = [_ for _ in range(len(S_GRID))]
				else:
					I_S = np.digitize([1e-5,args.selCoeff],S_GRID)
					S_GRID = [S_GRID[_] for _ in I_S]

				SAMPLING_TRANS = SAMPLING_TRANS[:,[ii_sel_last],:,:,:]
				if args.selCoeff != None:	
					SAMPLING_TRANS = SAMPLING_TRANS[I_S,:,:,:,:]
			else:
				#I_S = [_ for _ in range(0,len(S_GRID),len(S_GRID)//len(I_SEL))]	
				if args.selCoeff == None:
					I_S = [_ for _ in range(len(S_GRID))]
				else:
					I_S = np.digitize([1e-5,args.selCoeff],S_GRID)
				ii_sel_last = len(I_SEL) - 1
				if args.tSel == None:
					## ignore up to 100 gens before present
					#tlower = int(np.sum(AW_TIMES < 100))
					I_SEL = list(range(0,SAMPLING_TRANS.shape[1]-1))+[-1]
				else:
					I_SEL = [np.digitize(args.tSel,AW_TIMES)-1]
				S_GRID = [S_GRID[_] for _ in I_S]
				SAMPLING_TRANS = SAMPLING_TRANS[I_S,:,:,:,:]
				SAMPLING_TRANS = SAMPLING_TRANS[:,I_SEL,:,:,:]
			if args.debug:
				print('Randomized popfreq: %f'%(FREQS[discretizedPopFreqIdx]))
			
		else:
			raise NotImplementedError('Must enter popFreq')

		individualLogLRs = np.zeros((len(S_GRID),len(I_SEL),numImportanceSamples))
	Cder,Canc,Cmix = get_branches_all_classes(derTree,ancTree,mixTree,derInds,ancInds,ancHap,n,m,args.sitesFile)

	C = [Cder,Canc,Cmix]
	for l in range(len(C)):
		C[l] += [C[l][-1] for _ in range(len(ds) - len(C[l]) + 1)]
		C[l] = np.array(C[l])

	#continue
	logLikelihoodNullTarget = backward_algorithm(C,0,len(I_SEL)-1,popsize,n,m,ds)

	## conduct importance sampling to find sHat, tHat
	for (i_s,s) in enumerate(S_GRID):
		for (ii_sel,i_sel) in enumerate(I_SEL):
			individualLogLRs[i_s,ii_sel,k] = backward_algorithm(C,i_s,ii_sel,popsize,n,m,ds) #+ LOG_STAT_DISTN_DICT[s][discretizedPopFreqIdx] - LOG_STAT_DISTN_DICT[S_GRID[0]][discretizedPopFreqIdx]
			if args.statDistn:
				individualLogLRs[i_s,ii_sel,k] += SAMPLING_STAT_DISTN[i_s,ii_sel,discretizedPopFreqIdx] - np.log(BIN_SIZES[discretizedPopFreqIdx-1]) 
			dummy = forward_algorithm(C,i_s,ii_sel,popsize,n,m,ds)

			if args.debug:
				print('s: %.5f,\ttSel: %d,\t logL: %.3f'%(s,AW_TIMES[i_sel],individualLogLRs[i_s,ii_sel,k]))
			if np.isinf(individualLogLRs[i_s,ii_sel,k]) or np.isnan(individualLogLRs[i_s,ii_sel,k]):
				individualLogLRs[i_s,ii_sel,k] = -np.inf
				if i_s == 0 and ii_sel == 0:		
					numSamplesWronglyPolarized += 1
					if args.debug:
						print('Sample %d:\tIncorrect polarization'%(k))
			else:
				if i_s == 0 and ii_sel == 0:
					idxsSamplesCorrectlyPolarized += [k]
				for j in range(len(ds)):
					if j != 0:
						marg = TIME_ALPHA_DICT[(k,i_s,ii_sel,j)] + TIME_BETA_DICT[(k,i_s,ii_sel,j)]
					else:
						marg = TIME_ALPHA_DICT[(k,i_s,ii_sel,j)] 
					marg = marg - logsumexp(marg)	
					individualMargEsts[k,i_s,ii_sel,j,:] = marg
	if len(idxsSamplesCorrectlyPolarized) == 0:
		continue
	if idxsSamplesCorrectlyPolarized[-1] != k:
		continue

	# find most likely value of s, i_sel for this sample
	imax = np.unravel_index(individualLogLRs[:,:,k].argmax(), individualLogLRs[:,:,k].shape)
	ind_s_hat = S_GRID[imax[0]]
	ind_i_hats.append(imax[0])
	ind_i_sel_hat = I_SEL[imax[1]]
	ind_i_sel_hats.append(ind_i_sel_hat)
	ind_t_hat = AW_TIMES[ind_i_sel_hat+1]

	#import pdb; pdb.set_trace()

	individualFreqHat = FREQS[np.argmax(TIME_ALPHA_DICT[(k,imax[0],imax[1],imax[1]+1)] + TIME_BETA_DICT[(k,imax[0],imax[1],imax[1]+1)])]
	#import pdb; pdb.set_trace()
	
	if args.debug:
		print('Sample %d:\t%.6f\t%.1f\t%.3f'%(k,S_GRID[imax[0]],AW_TIMES[imax[1]],np.max(individualLogLRs[:,:,k])))

individualLogLRs[np.where(np.isnan(individualLogLRs))] = -np.inf

M =len(idxsSamplesCorrectlyPolarized)
logLikelihoodRatios = -np.log(len(idxsSamplesCorrectlyPolarized)) + logsumexp([individualLogLRs[:,:,k] - individualLogLRs[0,0,k] for k in idxsSamplesCorrectlyPolarized],axis=0) 
logLikelihoodRatios[np.where(np.isnan(logLikelihoodRatios))[0]] = -np.inf
if not args.selCoeff:
	idx = np.unravel_index(logLikelihoodRatios.argmax(), logLikelihoodRatios.shape)
	maxlr = np.max(logLikelihoodRatios)
	iHat = idx[0]
	sHat = S_GRID[iHat]

	jHat = idx[1]
	tHat = AW_TIMES[jHat+1]
else:
	if not args.ssv:
		iHat = 1
		jHat = 0
		sHat = args.selCoeff
		tHat = AW_TIMES[-1]
	else:
		raise NotImplementedError	
#max marginal trajectory
xHat = []
xHatLo = []
xHatHi = []
xMargs = []
if args.prior:
	if len(I_SEL) == 0:
		lebesgue_measure = np.concatenate(([1*(np.max(S_GRID) - np.min(S_GRID))],np.diff(S_GRID)))
		lebesgue_measure = np.log(lebesgue_measure)
		lebesgue_measure -= logsumexp(lebesgue_measure)
	else:
		lebesgue_measure_s = np.concatenate(([1*(np.max(S_GRID) - np.min(S_GRID))],np.diff(S_GRID)))
		lebesgue_measure_t = np.diff(AW_TIMES[[0] + I_SEL])
		lebesgue_measure = np.log(np.outer(lebesgue_measure_s,lebesgue_measure_t))  
		lebesgue_measure -= logsumexp(lebesgue_measure)
	posterior_s = lebesgue_measure + logLikelihoodRatios
	posterior_s -= logsumexp(posterior_s)
	print(posterior_s)
for j in range(len(ds)):
	if args.prior:
		marg = np.zeros((len(idxsSamplesCorrectlyPolarized),len(FREQS),len(S_GRID),len(I_SEL)))
	else:
		marg = np.zeros((len(idxsSamplesCorrectlyPolarized),len(FREQS)))
	for i,k in enumerate(idxsSamplesCorrectlyPolarized):
		if args.prior:
			for i_s in range(len(S_GRID)):
				for i_t in range(len(I_SEL)):
					marg[i,:,i_s,i_t] = individualMargEsts[k,i_s,i_t,j,:] + individualLogLRs[i_s,i_t,k] - individualLogLRs[0,0,k]	
		else:
			# importance sampling on trajs
			marg[i,:] = individualMargEsts[k,iHat,jHat,j,:] + individualLogLRs[iHat,jHat,k] - individualLogLRs[0,0,k] 
	marg = logsumexp(marg,axis=0)
	if args.prior:
		marg = logsumexp(marg + posterior_s,axis=(1,2))		
		marg -= logsumexp(marg)
	else:	
		marg -= logsumexp(marg)

	xMargs.append(marg)
	distn = stats.rv_discrete(a=0,b=1,values=(FREQS,np.exp(marg)))	

	m = FREQS[np.argmax(marg)]
	I = distn.interval(0.95)
	l = I[0]
	h = I[1]
	xHat.append(m)
	xHatLo.append(l)
	xHatHi.append(h)
if args.debug:
	print('t = [%s]'%(','.join(['%.3f'%(x) for x in AW_TIMES])))
print_results(args)
write_results_to_h5(args)
