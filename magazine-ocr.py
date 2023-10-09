#!/usr/bin/python3
from PIL import Image
import PIL
import glob
import os
import sys
import argparse
import tempfile
import re
import multiprocessing
from multiprocessing import Process
import ocrmypdf
import shutil

def getSortedFiles(inputDir, fileSpec, sortAlgorithm):
    inputDir = os.path.dirname(inputDir)


    files = []
    if fileSpec is None:
        for fs in [ '*.jpg', '*.JPG', '*.png', '*.PNG', '*.tif', '*.TIF' ]:
            files += glob.glob("%s/%s" % (inputDir, fs))
    else:
        files += glob.glob("%s/%s" % (inputDir, fileSpec))

    if sortAlgorithm == 'name':
        files = sorted(files)
    elif sortAlgorithm == 'date':
        # Get the modification time from each file 
        filesByTime = { }
        for f in files:
            t = os.path.getmtime(f)
            filesByTime[t] = f
        
        oldNumFiles = len(files)
        
        files = [ ]
        for t in sorted(list(set(filesByTime.keys()))):
            files.append(filesByTime[t])
        
        if len(files) != oldNumFiles:
            printf("ERROR:  Sorting by time failed, multiple files at same timestamp")
            sys.exit(1)
    else:
        printf("Unknown sort algorithm [%s], I give up")
        sys.exit(1)

    return files


def buildPageMap(files, splitAlgorithm, frontTransforms, backTransforms, allTransforms):
    # The purpose of this function is to take the sorted list of files and turn that into
    #  the pages we're going to use to reassemble the magazine, along with any transforms we need
    pageMap = [ ]

    if frontTransforms is None:
        frontTransforms = ""

    if backTransforms is None:
        backTransforms = ""

    if allTransforms is None:
        allTransforms = ""


    totalFiles = len(files)
    totalPages = 0
    algoText = "NONE"

    print("[PAGE MAPPING: START]  %d scans" % (totalFiles))

    if splitAlgorithm == 'fbfb':
        if totalFiles % 2 != 0:
            print("ERROR: Have an odd number of scans, that doesn't work!");
            sys.exit(2)

        algoText = "FBFB"

        totalPages = totalFiles * 2
        
        pageMap = [{'srcFile':None, 'transforms':None, 'srcHalf':None } for i in range(0,totalPages)]

        # This is for scanners that produce a scan of the front, then the back, then the front, then the back, of
        # a de-bound magazine or book.
        # File 0 (1F)  - Page halves [n-1:0]
        # File 1 (1B)  - Page halves [1:n-2]
        # File 2 (2F)  - Page halves [n-3:2]
        # File 3 (2B)  - Page halves [3:n-4]

        for p in range(0, totalPages//2):
            if p % 2 == 0:
                # This is a front page scan
                pageMap[p]['srcFile'] = files[p]
                pageMap[p]['srcHalf'] = 'right'
                pageMap[p]['transforms'] = frontTransforms + allTransforms
                pageMap[totalPages - p - 1]['srcFile'] = files[p]
                pageMap[totalPages - p - 1]['srcHalf'] = 'left'
                pageMap[totalPages - p - 1]['transforms'] = frontTransforms + allTransforms
            else:
                # This is a back page scan
                pageMap[p]['srcFile'] = files[p]
                pageMap[p]['srcHalf'] = 'left'
                pageMap[p]['transforms'] = backTransforms + allTransforms
                pageMap[totalPages - p - 1]['srcFile'] = files[p]
                pageMap[totalPages - p - 1]['srcHalf'] = 'right'
                pageMap[totalPages - p - 1]['transforms'] = backTransforms + allTransforms

    elif splitAlgorithm == 'ffbb':
        # This is for scanners that produce a scan of all the fronts, then all the backs, 
        # of a de-bound magazine or book.
        # File 0 (1F)  - Page halves [n-1:0]
        # File 1 (2F)  - Page halves [n-3:2]
        # File 2 (2F)  - Page halves [n-5:4]
        # ...
        # File x (xB)  - Page halves [5:n-6]
        # File y (yB)  - Page halves [3:n-4]
        # File z (zB)  - Page halves [1:n-2]
        if totalFiles % 2 != 0:
            print("ERROR: Have an odd number of scans, that doesn't work!");
            sys.exit(2)

        algoText = "FFBB"
        totalPages = totalFiles * 2
        
        pageMap = [{'srcFile':None, 'transforms':None, 'half':None } for i in range(0,totalPages)]
        # Each page - source file, pre-transforms, left or right half

        for f in range(0, totalFiles):
            p = f * 2   # Lower working page number is always fileNum * 2
            if f < totalFiles//2:
                # This is a front page scan
                pageMap[p]['srcFile'] = files[f]
                pageMap[p]['srcHalf'] = 'right'
                pageMap[p]['transforms'] = frontTransforms + allTransforms
                pageMap[totalPages - p - 1]['srcFile'] = files[f]
                pageMap[totalPages - p - 1]['srcHalf'] = 'left'
                pageMap[totalPages - p - 1]['transforms'] = frontTransforms + allTransforms
            else:
                # This is a back page scan
                pageMap[p]['srcFile'] = files[f]
                pageMap[p]['srcHalf'] = 'left'
                pageMap[p]['transforms'] = backTransforms + allTransforms
                pageMap[totalPages - p - 1]['srcFile'] = files[f]
                pageMap[totalPages - p - 1]['srcHalf'] = 'right'
                pageMap[totalPages - p - 1]['transforms'] = backTransforms + allTransforms

    else:
        print("ERROR:  Unknown page split algorithm [%s], exiting..." % (splitAlgorithm))
        sys.exit(1)

    print("[PAGE MAPPING: DONE]  %d scans -> %d pages using [%s]" % (totalFiles, totalPages, algoText))
        
    return pageMap

def imageTransform(debugLvl, fname, srcImg, transformCmds):
    rotateRegex = re.compile('r(?P<degrees>[0-9]+)(?P<remaining>.*)')
    cropRegex = re.compile('c(?P<x_size>[0-9]+)x(?P<y_size>[0-9]+)\+(?P<x_offset>[0-9]+)\+(?P<y_offset>[0-9]+)(?P<remaining>.*)')
    resizeAbsoluteRegex = re.compile('s(?P<x_size>[0-9]+)x(?P<y_size>[0-9]+)(?P<remaining>.*)')
    resizePercentRegex = re.compile('s(?P<percent>[0-9]+)%(?P<remaining>.*)')
    
    if transformCmds is None or 0 == len(transformCmds):
        return srcImg

    if debugLvl > 0:
        print("  XFORM [%s] = [%s]" % (fname, transformCmds))

    newImg = srcImg    

    nextCmds = transformCmds
    while nextCmds is not None and len(nextCmds):
        remainingCmds = nextCmds
        nextCmds = None

        rotateMatch = rotateRegex.match(remainingCmds)
        if rotateMatch is not None:
            # Do rotate
            degrees = int(rotateMatch.group('degrees'))
            if debugLvl > 0:            
                print("  XFORM [%s]:  Rotate %d degrees" % (fname, degrees))
            newImg = newImg.rotate(degrees, PIL.Image.LANCZOS, expand=1)
            nextCmds = rotateMatch.group('remaining')
            continue

        cropMatch = cropRegex.match(remainingCmds)
        if cropMatch is not None:
            # Do crop
            new_x_size = int(cropMatch.group('x_size'))
            new_y_size = int(cropMatch.group('y_size'))
            new_x_offset = int(cropMatch.group('x_offset'))
            new_y_offset = int(cropMatch.group('y_offset'))
            
            x_size,y_size = newImg.size
            if debugLvl > 0:            
                print("  XFORM [%s]:  Crop %dx%d to %dx%d+%d+%d" % (fname, x_size, y_size, new_x_size, new_y_size, new_x_offset, new_y_offset))
            # FIXME:  Probably should do some sanity checking here?
            newImg = newImg.crop((new_x_offset, new_y_offset, new_x_offset + new_x_size, new_y_offset + new_y_size))


            nextCmds = cropMatch.group('remaining')
            continue
    
        resizeAbsoluteMatch = resizeAbsoluteRegex.match(remainingCmds)
        if resizeAbsoluteMatch is not None:
            # Do resize
            new_x_size = int(resizeAbsoluteMatch.group('x_size'))
            new_y_size = int(resizeAbsoluteMatch.group('y_size'))
            x_size,y_size = newImg.size
            if debugLvl > 0:            
                print("  XFORM [%s]:  Absolute resize %dx%d to %dx%d" % (fname, x_size, y_size, new_x_size, new_y_size))
            newImg = newImg.resize((new_x_size, new_y_size), PIL.Image.LANCZOS)
            nextCmds = resizeAbsoluteMatch.group('remaining')
            continue

        resizePercentMatch = resizePercentRegex.match(remainingCmds)
        if resizePercentMatch is not None:
            # Do resize
            new_size = int(resizePercentMatch.group('percent'))
            x_size,y_size = newImg.size
            new_x_size = (x_size * new_size) // 100
            new_y_size = (y_size * new_size) // 100
            if debugLvl > 0:            
                print("  XFORM [%s]:  Percent (%d) resize %dx%d to %dx%d" % (fname, new_size, x_size, y_size, new_x_size, new_y_size))
            newImg = newImg.resize((new_x_size, new_y_size), PIL.Image.LANCZOS)
            nextCmds = resizePercentMatch.group('remaining')
            continue

    return newImg

def createPageProcess(pageTuple):
    (debugLvl, tmpWorkingDir, pageNum, pageData) = pageTuple
    print("[PAGE] Creating page %04d " % (pageNum))
    
    if debugLvl > 0:
        print("  [CREATE] Processing file %s" % (pageData['srcFile']))
    srcImg = Image.open(pageData['srcFile'], mode='r')
    # Do base transformations (rotate, crop, resize)
    img = imageTransform(debugLvl, os.path.basename(pageData['srcFile']), srcImg, pageData['transforms'])
    width,height = img.size            
    # cut this sucker in half for left/right
    if pageData['srcHalf'] == 'left':
        img = img.crop((0,0,width/2,height))
    elif pageData['srcHalf'] == 'right':
        img = img.crop((width/2,0,width,height))
    elif page['srcHalf'] == 'all':
        pageData  # do nothing, we're using the whole page
    else:
        print("ERROR:  Don't know what to do with srcHalf of [%s]" % (pageData['srcHalf']))
        sys.exit(3)

    pageFilenameBase = "page-%04d.png" % (pageNum+1)
    if debugLvl > 0:
        print("  [CREATE] Saving page as %s" % (pageFilenameBase))
    
    pageFilename = os.path.join(tmpWorkingDir, pageFilenameBase)
    img.save(pageFilename)
    if debugLvl > 0:
        print("  [CREATE] Done")
    srcImg.close()
    
    return (pageNum, pageFilename)
    
def createPagesMultiprocess(debugLbl, pageMap, tmpWorkingDir):
    print("[PAGE] Creating %d pages from source images - multithreaded" % (len(pageMap)))
    pageInputTupleList = []
    for pageNum, pageData in enumerate(pageMap):
        pageInputTupleList.append((debugLbl, tmpWorkingDir, pageNum, pageData))
    
    pool = multiprocessing.Pool()
    pageResultTupleList = pool.map(createPageProcess, pageInputTupleList)
    
    for (pageNum, pageFilename) in pageResultTupleList:
        pageMap[pageNum]['pageFilename'] = pageFilename
    print("[PAGE] Done")

def createPages(debugLvlpageMap, tmpWorkingDir):
    # FIXME:  Make this loop run in parallel - no reason not to use multicore if available
    for pageNum, pageData in enumerate(pageMap):
        print("[PAGE] Creating page %04d " % (pageNum))
        
        print("  [CREATE] Processing file %s" % (pageData['srcFile']))
        srcImg = Image.open(pageData['srcFile'], mode='r')
        # Do base transformations (rotate, crop, resize)
        img = imageTransform(os.path.basename(pageData['srcFile']), srcImg, pageData['transforms'])
        width,height = img.size            
        # cut this sucker in half for left/right
        if pageData['srcHalf'] == 'left':
            img = img.crop((0,0,width/2,height))
        elif pageData['srcHalf'] == 'right':
            img = img.crop((width/2,0,width,height))
        elif page['srcHalf'] == 'all':
            pageData  # do nothing, we're using the whole page
        else:
            print("ERROR:  Don't know what to do with srcHalf of [%s]" % (pageData['srcHalf']))
            sys.exit(3)

        pageFilenameBase = "page-%04d.png" % (pageNum+1)
        print("  [CREATE] Saving page as %s" % (pageFilenameBase))
        
        pageFilename = os.path.join(tmpWorkingDir, pageFilenameBase)
        img.save(pageFilename)
        pageMap[pageNum]['pageFilename'] = pageFilename
        print("  [CREATE] Done")
        srcImg.close()

def createPDF(debugLvl, pageMap, tmpWorkingDir, quality=80, dpi=300):
    pdfImages = []

    print("[PDF] Start")    
    for page in pageMap:
        i = Image.open(page['pageFilename'], 'r')
        i.convert('RGB')
        i.info['dpi'] = (dpi,dpi)
        pdfImages.append(i)

    pdfFilename = os.path.join(tmpWorkingDir, "output.pdf")
    print("[PDF] Creating intermediate PDF [%s]" % (pdfFilename))

    pdfImages[0].save(pdfFilename, "PDF", quality=quality, resolution=dpi, save_all=True, append_images=pdfImages[1:])
    print("[PDF] Done")
    
    return pdfFilename

def ocrPDF(debugLvl, nonOcrPdfFilename, ocrPdfFilename):
    print("[OCR] Start")
    ocrmypdf.ocr(nonOcrPdfFilename, ocrPdfFilename, output_type='pdfa', pdfa_image_compression='jpeg', jobs=os.cpu_count(), jpg_quality=80, deskew=True)
    print("[OCR] Done")
    return ocrPdfFilename

def main(args, cmdstr):
    debugLvl = int(args['debugVerbosity'])

    # Sanitize and sane-ify the output paths
    outputFilePath = args['outputPdfName']

    if outputFilePath is not None:
        outputPdfName = os.path.basename(outputFilePath)
        outputDir = os.path.dirname(outputFilePath)
        outputBaseName = os.path.splitext(outputPdfName)[0]

    if outputPdfName is None or outputDir is None or outputBaseName is None or len(outputPdfName) == 0:
        print("ERROR:  Must specify output PDF name with -o")
        sys.exit(1)
    
    print("Setting output paths:")
    print("  Output PDF name    [%s]" % (outputPdfName))
    print("  Output Directory   [%s]" % (outputDir))
    print("  Output Archive Dir [%s]" % (outputBaseName))
    
    if len(outputBaseName) == 0:
        print("ERROR:  [%s] is a stupid filename, try again with something but an extension" % (outputPdfName))
        sys.exit(1)
    
    if not os.path.exists(outputDir):
        print("ERROR:  Output directory does not exist [%s]" % (outputDir))
        sys.exit(1)
    
    
    ##############################
    #   Step 1 - Create sorted list of scanned input files from inputDir
    
    inputDir = os.path.dirname(args['inputDir'])
    sortedFiles = getSortedFiles(args['inputDir'], args['fileSpec'], args['sort'])
    if (debugLvl > 1):
        for fileNum,fileName in enumerate(sortedFiles):
            print("  File %04d : [%s]" % (fileNum, os.path.basename(fileName)))

    ##############################
    #   Step 2 - Create page list and mapping between source files and individual page pieces

    pageMap = buildPageMap(sortedFiles, args['split'], args['frontPageTransforms'], args['backPageTransforms'], args['allPageTransforms'])
    if (debugLvl > 1):
        for pageNum,pageData in enumerate(pageMap):
            print("  Page %04d : [%s:%s]" % (pageNum, os.path.basename(pageData['srcFile']), pageData['srcHalf']))
        
    tmpWorkingDir = tempfile.mkdtemp(None, "magsplit_", None)
    print("[PAGE] Created temporary working dir [%s]" % (tmpWorkingDir))

    ##############################
    #   Step 3 - Actually generate page images from source files
    
    createPagesMultiprocess(debugLvl, pageMap, tmpWorkingDir)
    # This is the single-process version - probably remove?
    #createPages(pageMap, tmpWorkingDir)

    ##############################
    #   Step 4 - Create raw temp PDF from page images

    nonOcrPdfName = createPDF(debugLvl, pageMap, tmpWorkingDir, int(args['jpegQuality']), int(args['dpi']))

    ##############################
    #   Step 5 - OCR the temp PDF and save to final destination

    outputPdfPath = os.path.join(outputDir, outputPdfName)
    ocrPdfName = ocrPDF(debugLvl, nonOcrPdfName, outputPdfPath)

    ##############################
    #   Step 6 - Archive off build cmd and source images

    # Generate archive if so requested
    if args['outputArchive'] is True:
        archiveDirName = os.path.join(outputDir, outputBaseName)
        print("[ARCHIVE]  Building source data archive at [%s]" % (archiveDirName))

        if not os.path.exists(archiveDirName):
            os.mkdir(archiveDirName)
        
        if not os.path.isdir(archiveDirName):
            print("ERROR:  Cannot generate archive, [%s] not directory" % archiveDirName)
        else:
            archiveCmdTextFilename = os.path.join(outputDir, outputBaseName, "magazine-split-cmd.txt")
            with open(archiveCmdTextFilename, "w") as f:
                f.write(cmdstr)
                f.write('\n')
                f.flush()

            for imgFile in sortedFiles:
                newFile = os.path.join(archiveDirName, os.path.basename(imgFile))
                shutil.copy2(imgFile, newFile)
        print("[ARCHIVE] Done")

    ##############################
    #   Step 7 - Clean up our temporary directory mess
    #   Unless we're in debug mode >= 2, in which case leave it for debugging
    if debugLvl < 2:
        print("[CLEANUP]  Removing temp files/directory")

        filesToRemove = os.listdir(tmpWorkingDir)
        for f in filesToRemove:
            os.remove(os.path.join(tmpWorkingDir, f))
        os.rmdir(tmpWorkingDir)
   
    print("[SUCCESS]  Output at [%s]" % (ocrPdfName))


if __name__ == "__main__":
    # calling main function
    parser = argparse.ArgumentParser(description="Process a directory of scanned magazine pages into individual images")
    parser.add_argument('-i', nargs='?', default='./input/', dest='inputDir')
    parser.add_argument('-o', nargs='?', default='./conversion_output.pdf', dest='outputPdfName')
    parser.add_argument('-a', default=True, dest='outputArchive', action=argparse.BooleanOptionalAction)
    parser.add_argument('-j', nargs='?', default='80', dest='jpegQuality' )
    parser.add_argument('-d', nargs='?', default='300', dest='dpi' )
    parser.add_argument('-s', nargs='?', default='name', dest='sort' )
    parser.add_argument('-f', nargs='?', default=None, dest='fileSpec' )
    parser.add_argument('-m', nargs='?', default=None, dest='split' )
    
    parser.add_argument('-v', nargs='?', default='0', dest='debugVerbosity' )
    parser.add_argument('-x', nargs='?', default=None, dest='frontPageTransforms' )
    parser.add_argument('-y', nargs='?', default=None, dest='backPageTransforms' )
    parser.add_argument('-z', nargs='?', default=None, dest='allPageTransforms' )
    args = vars(parser.parse_args())
    cmdstr = ' '.join(sys.argv)
    main(args, cmdstr)
  
