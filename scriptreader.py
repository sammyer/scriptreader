# -*- coding: utf-8 -*-
"""
Created on Sat Jul 23 15:19:16 2016

@author: sam
"""
import codecs,os,sys
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfdevice import PDFDevice
from pdfminer.layout import LAParams
from pdfminer.converter import PDFPageAggregator, PDFConverter, PDFLayoutAnalyzer
from pdfminer.layout import *

def concat(arr):
	arr2=[]
	for i in arr: arr2.extend(i)
	return arr2

#Same as TFLine but without extra data
class TextLine:
	def __init__(self,line):
		self.x0=line.x0
		self.x1=line.x1
		self.y0=line.y0
		self.text=line.get_text()
	
	def get_text(self):
		return self.text

class Cluster:
	def __init__(self,pos,centered,count=0):
		self.pos=pos
		self.centered=centered
		self.count=count
	
	def dist(self,line):
		if self.centered:
			linePos=(line.x0+line.x1)*0.5
		else:
			linePos=line.x0
		return abs(linePos-self.pos)
	
	def __repr__(self):
		return "pos=%s center=%s count=%d"%(self.pos,self.centered,self.count)

class CountMap:
	def __init__(self):
		self.data={}
	
	def add(self,k):
		try:
			self.data[k]+=1
		except:
			self.data[k]=1
	
	def delete(self,k):
		try: del self.data[k]
		except: pass
	
	def items(self):
		return sorted(self.data.items(),key=lambda x:-x[1])
	
	def get(self,k):
		try: return self.data[k]
		except: return 0

class Clustering:
	def __init__(self,lines):
		self.speakerCluster=None
		self.dialogueCluster=None
		self.radius=4
		self.clusters=self.clusterPositions(lines)
		self.analyzeClusters(self.clusters)
	
	def capsPercent(self,s):
		upperCount=0
		lowerCount=0
		for c in s:
			if c>='a' and c<='z': lowerCount+=1
			if c>='A' and c<='Z': upperCount+=1
		total=upperCount+lowerCount
		if total==0: return 0
		else: return upperCount/float(total)
	
	def capsPercentLines(self,lines):
		return sum(map(lambda line:self.capsPercent(line.get_text()),lines))/len(lines)
	
	def clusterPositions(self,lines):
		leftMap=CountMap()
		centerMap=CountMap()
		for line in lines:
			left=int(round(line.x0))
			center=int(round(0.5*(line.x0+line.x1)))
			leftMap.add(left)
			centerMap.add(center)
			
		#group by radius
		self.clusters=[]
		
		for cmap in leftMap,centerMap:
			keysLeft=set(cmap.data.keys())
			for pos,count in cmap.items():
				if pos not in keysLeft: continue
				keysLeft.remove(pos)
				for nearby in range(pos-self.radius,pos+self.radius+1):
					if nearby in keysLeft:
						cmap.data[pos]+=cmap.data[nearby]
						del cmap.data[nearby]
						keysLeft.remove(nearby)
				self.clusters.append(Cluster(pos,cmap==centerMap,cmap.data[pos]))
		self.clusters.sort(key=lambda x:x.count,reverse=True)
		self.clusters=self.clusters[:8]
	
		#count lines that can only be assigned to one cluster	
		for cluster in self.clusters:
			cluster.count=0
		for line in lines:
			cand=[cluster for cluster in self.clusters if cluster.dist(line)<self.radius]
			if len(cand)==1:
				cand[0].count+=1
		self.clusters.sort(key=lambda x:x.count,reverse=True)
		
		#redo count, so that each line is assigned to only one cluster
		for cluster in self.clusters:
			cluster.count=0
		for line in lines:
			for cluster in self.clusters:
				if cluster.dist(line)<self.radius: 
					cluster.count+=1
					break
		self.clusters.sort(key=lambda x:x.count,reverse=True)
		return self.clusters

	def assignCluster(self,line):
		cand=[cluster for cluster in self.clusters if cluster.dist(line)<self.radius]
		if len(cand)==0: return None
		if len(cand)==1: return cand[0]
		return min(cand,key=lambda x:x.dist(line)+(2 if x.centered else 0))
	
	def analyzeClusters(self,clusters):
		top3=clusters[:3]
		top3.sort(key=lambda x:x.pos)
		self.speakerCluster=top3[2]
		self.dialogueCluster=top3[1]
	
	def isSpeaker(self,line):
		return self.assignCluster(line)==self.speakerCluster
		
	def isDialogue(self,line):
		return self.assignCluster(line)==self.dialogueCluster

class Writer:
	def __init__(self,filename):
		self.state=0
		self.f=codecs.open(filename,'w',"cp1252",errors='ignore')
		self.speaker=""
		self.dialogue=""
	
	def addSpeaker(self,s):
		s=s.replace(u'\n',u'')
		if self.state==2:
			self.writeLine()
		if self.state==1: self.speaker+=s
		else:
			self.speaker=s
			self.dialogue=""
		self.state=1
	
	def addDialogue(self,s):
		s=s.replace(u'\n',u'')
		if self.state!=0: self.dialogue+=s
		self.state=2


	def escapeStr(self,s):
		return u'"'+s.replace(u'"',u'""')+u'"'
		
	def writeLine(self):
		line=self.escapeStr(self.speaker)+u','+self.escapeStr(self.dialogue)+u'\n'
		self.f.write(line)
		
	def close(self):
		if self.state==2: self.writeLine()
		self.f.close()

class Extractor:
	def __init__(self):
		self.buffer=[]
		self.clusters=None
		self.writer=None
		
	def convert(self,filename):
		csvFile=filename.replace('.pdf','.csv')
		self.writer=Writer(csvFile)
		self.readLines(filename)
		self.writeLines()
	
	def getTextLines(self,layout):
		if isinstance(layout,LTTextLine):
			if len(layout.get_text().strip())==0: return []
			return [TextLine(layout)]
		else:
			arr=[]
			try:
				for child in layout:
					arr.extend(self.getTextLines(child))
			except Exception as e:
				pass
			return arr
	
	def readLines(self,filename,numPages=0):
		# Open a PDF file.
		fp = open(filename, 'rb')
		# Create a PDF parser object associated with the file object.
		parser = PDFParser(fp)
		# Create a PDF document object that stores the document structure.
		# Supply the password for initialization.
		document = PDFDocument(parser)
		# Check if the document allows text extraction. If not, abort.
		if not document.is_extractable:
		    raise PDFTextExtractionNotAllowed
		# Create a PDF resource manager object that stores shared resources.
		rsrcmgr = PDFResourceManager()
		# Create a PDF device object.
		#device = PDFDevice(rsrcmgr)
		# Create a PDF interpreter object.
		#interpreter = PDFPageInterpreter(rsrcmgr, device)
		# Process each page contained in the document.
		#for page in PDFPage.create_pages(document):
		#    interpreter.process_page(page)
							
		# Set parameters for analysis.
		laparams = LAParams()
		# Create a PDF page aggregator object.
		device = PDFPageAggregator(rsrcmgr, laparams=laparams)
		interpreter = PDFPageInterpreter(rsrcmgr, device)
		layouts=[]
		pageNum=0
		for page in PDFPage.create_pages(document):
			interpreter.process_page(page)
			# receive the LTPage object for the page.
			layout = device.get_result()
			lines = self.getTextLines(layout)
			self.buffer.append(lines)
			pageNum+=1
			if numPages>0 and pageNum==numPages: break
			
		fp.close()
		return layouts
	
	def writeLines(self):
		testLines=[]
		for lines in self.buffer[5:15]: testLines.extend(lines)
		self.clusters=Clustering(testLines)
		for lines in self.buffer:
			lines.sort(key=lambda line:-line.y0)
			for line in lines:
				if self.clusters.isSpeaker(line):
					self.writer.addSpeaker(line.get_text())
				elif self.clusters.isDialogue(line):
					self.writer.addDialogue(line.get_text())
		self.writer.close()


def extractAll(rootDir='.'):
	for filename in os.listdir(rootDir):
		if filename.endswith('.pdf'):
			extractor=Extractor()
			print ("\nExtracting "+filename)
			extractor.convert(os.path.join(rootDir,filename))
			
if __name__ == "__main__":
	if len(sys.argv)>1:
		extractAll(sys.argv[1])
	else:
		extractAll()

