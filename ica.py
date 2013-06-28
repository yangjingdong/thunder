# ica <master> <inputFile> <outputFile_Components> <outputFile_Weights>
# 
# perform ica on a data matrix.
# input is a local text file or a file in HDFS
# format should be rows of ' ' separated values
# - example: space (rows) x time (cols)
# - rows should be whichever dim is larger
# 'k' is number of principal components to use in initial dim reduction
# 'c' is the number of ica components to return
# writes unmixing matrix and independent components to text

import sys
from numpy import *
from scipy.linalg import *
from pyspark import SparkContext

if len(sys.argv) < 6:
  print >> sys.stderr, \
  "(ica) usage: ica <master> <inputFile> <outputFile> <k> <c>"
  exit(-1)

def parseVector(line):
    return array([float(x) for x in line.split(' ')])

# parse inputs
sc = SparkContext(sys.argv[1], "ica")
lines = sc.textFile(sys.argv[2])
outputFile = str(sys.argv[3])
k = int(sys.argv[4])
c = int(sys.argv[5])

# compute covariance matrix
print "(ica) computing data covariance"
data = lines.map(parseVector).cache()
n = data.count()
m = len(data.first())
meanVec = data.reduce(lambda x,y : x+y) / n
sub = data.map(lambda x : x - meanVec)
cov = sub.map(lambda x : outer(x,x)).reduce(lambda x,y : (x + y)) / n

# do eigenvector decomposition
print "(ica) doing eigendecomposition"
w, v = eig(cov)
inds = argsort(w)[::1]
kEigVecs = v[:,inds[0:k]]
kEigVals = w[inds[0:k]]

# whiten data
print "(ica) whitening data"
whtMat = real(dot(inv(sqrtm(diag(kEigVals))),transpose(kEigVecs)))
unwhtMat = real(dot(kEigVecs,sqrtm(diag(kEigVals))))
wht = sub.map(lambda x : dot(whtMat,x))

# do multiple independent component extraction
print "(ica) starting iterative ica"
B = orth(random.randn(k,c))
Bold = zeros((k,c))
iterNum = 0
minAbsCos = 0
termTol = 0.0001
iterMax = 1000
errVec = zeros(iterMax)

while (iterNum < iterMax) & ((1 - minAbsCos) > termTol):
	iterNum += 1
	print "(ica) starting iteration " + str(iterNum)
	# update rule for pow3 nonlinearity (todo: add other nonlins)
	B = wht.map(lambda x : outer(x,dot(x,B) ** 3)).reduce(lambda x,y : x + y) / n - 3 * B
	print "(ica) orthogonalizing"
	# orthognalize
	B = dot(B,real(sqrtm(inv(dot(transpose(B),B)))))
	# evaluate error
	minAbsCos = min(abs(diag(dot(transpose(B),Bold))))
	# store results
	Bold = B
	errVec[iterNum-1] = (1 - minAbsCos)

# get unmixing matrix
W = dot(transpose(B),whtMat)

# save output files
print("(ica) finished after "+str(iterNum)+"iterations")
print("(ica) writing output...")
savetxt("out-W-"+outputFile+".txt",W,fmt='%.8f')
for ic in range(0,c):
	# get unmixed signals
	sigs = wht.map(lambda x : dot(dot(W[ic,:],unwhtMat),x)).collect()
	savetxt("out-sigs-"+str(ic)+"-"+outputFile+".txt",sigs,fmt='%.8f')


