# last edited: 03/08/2017, 15:00

import os,sys
import glob
sys.path.append(os.path.join(os.getenv('XChemExplorer_DIR'),'lib'))

from XChemUtils import parse


# - select datasets with highest resolution
# - select only those without an event map
# - take the one with the lowest Rfree


def find_highest_resolution_datasets(panddaDir):
    found=False
    datasetList=[]
    for logFile in glob.glob(os.path.join(panddaDir,'logs','*.log')):
        for n,line in enumerate(open(logFile)):
            if line.startswith('Statistical Electron Density Characterisation') and len(line.split()) == 6:
                resolution=line.split()[5]
                found=True
                foundLine=n
            if found and n>=foundLine+3:
                if line.startswith('---'):
                    break
                else:
                    tmpLine=line.replace(' ','').replace('\t','').replace('\n','').replace('\r','')
                    for item in tmpLine.split(','):
                        if item != '':
                            datasetList.append(item)
    print datasetList
    return datasetList

def get_datasets_without_event_map(panddaDir,datasetList):
    datasetListwithoutEvent=[]
    for dataset in datasetList:
        noEvent=True
        for files in glob.glob(os.path.join(panddaDir,'processed_datasets',dataset,'*')):
            if 'event' in files:
                noEvent=False
                break
        if noEvent:
            datasetListwithoutEvent.append(dataset)
    print datasetListwithoutEvent
    return datasetListwithoutEvent

def select_dataset_with_lowest_Rfree(panddaDir,datasetListwithoutEvent):
    datasetList=[]
    lowestRfree=''
    for dataset in datasetListwithoutEvent:
        if os.path.isfile(os.path.join(panddaDir,'processed_datasets',dataset,dataset+'-pandda-input.pdb')):
            stats=parse().PDBheader(os.path.join(panddaDir,'processed_datasets',dataset,dataset+'-pandda-input.pdb'))
            Rfree=stats['Rfree']
            try:
                print dataset,Rfree,stats['ResolutionHigh']
                datasetList.append([dataset,float(Rfree)])
            except ValueError:
                pass
    if datasetList != []:
        lowestRfree=min(datasetList,key=lambda x: x[1])[0]
    return lowestRfree

def link_pdb_mtz_files(panddaDir,lowestRfree):
    targetDir='/'.join(panddaDir.split('/')[:len(panddaDir.split('/'))-2])
    panddaFolder=panddaDir.split('/')[len(panddaDir.split('/'))-2]
    print targetDir
    print panddaFolder
#    if os.path.isfile(os.path.join(panddaDir,'processed_datasets',lowestRfree,lowestRfree+'-pandda-input.pdb')):


if __name__=='__main__':
    panddaDir=sys.argv[1]
    datasetList=find_highest_resolution_datasets(panddaDir)
    datasetListwithoutEvent=get_datasets_without_event_map(panddaDir,datasetList)
    lowestRfree=select_dataset_with_lowest_Rfree(panddaDir,datasetListwithoutEvent)
    link_pdb_mtz_files(panddaDir,lowestRfree)