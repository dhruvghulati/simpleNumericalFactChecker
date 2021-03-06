'''

TODO - this needs to really sort out the problems with too many training instances for region/value slots e.g. duplicates for Democratic Republic of Congo, however have fixed problem with parsed sentence including duplicate slots (so better for bag of words)
http://stackoverflow.com/questions/38509239/need-to-remove-items-from-both-a-list-and-a-dictionary-of-tuple-value-pairs-at-s

data/train_jsons
data/output/sentenceRegionValueDep.json
data/locationNames
data/output/sentenceSlotsFilteredDep.json
data/output/sentenceSlotsDiscardDep.json
0.3

'''

import json
import sys
import glob
import networkx
import re
import copy
import numpy
import codecs
import itertools
from nltk.text import Text


def getShortestDepPaths(sentenceDAG, locationTokenIDs, numberTokenIDs):
    shortestPaths = []
    for locationTokenID in locationTokenIDs:
        for numberTokenID in numberTokenIDs:
            try:
                # get the shortest paths
                # get the list as it they are unlikely to be very many and we need to len()
                tempShortestPaths = list(networkx.all_shortest_paths(sentenceDAG, source=locationTokenID, target=numberTokenID))
                # print "Temporary shortest path between ",numberTokenID,"and ",locationTokenID,"is ",tempShortestPaths
                # if the paths found are shorter than the ones we had (or we didn't have any)
                if (len(shortestPaths) == 0) or len(shortestPaths[0]) > len(tempShortestPaths[0]):
                    shortestPaths = tempShortestPaths
                # if they have equal length add them
                elif len(shortestPaths[0]) == len(tempShortestPaths[0]):
                    shortestPaths.extend(tempShortestPaths)
            # if not paths were found, do nothing
            except networkx.exception.NetworkXNoPath:
                pass
    # print "Shortest paths are",shortestPaths
    return shortestPaths

# given the a dep path defined by the nodes, get the string of the lexicalized dep path, possibly extended by one more dep
# This is non-extended so far
def depPath2StringExtend(sentenceDAG, path, locationTokenIDs, numberTokenIDs, extend=False):
    # path is the shortest path
    strings = []
    # this keeps the various bits of the string
    pathStrings = []
    # get the first dep which is from the location
    # print "Path 0 is ",path[0]
    # print "Path 1 is ",path[1]
    pathStrings.append("LOCATION_SLOT~" + sentenceDAG[path[0]][path[1]]["label"])
    # for the words in between add the lemma and the dep
    hasContentWord = False
    for seqOnPath, tokenId in enumerate(path[1:-1]):
        if sentenceDAG.node[tokenId]["ner"] == "O":
            pathStrings.append(sentenceDAG.node[tokenId]["word"].lower() + "~" + sentenceDAG[tokenId][path[seqOnPath+2]]["label"])
            if sentenceDAG.node[tokenId]["pos"][0] in "NVJR":
                hasContentWord = True
        else:
            pathStrings.append(sentenceDAG.node[tokenId]["ner"] + "~" + sentenceDAG[tokenId][path[seqOnPath+2]]["label"])

    pathStrings.append("NUMBER_SLOT")

    if hasContentWord:
        strings.append("+".join(pathStrings))

    # print "String is ",strings

    if extend:
        # create additional paths by adding all out-edges from the number token (except for the ones on the path)
        # the extension is always added left of the node
        for nodeOnPath in path:
            # go over each node on the path
            outEdges = sentenceDAG.out_edges_iter([nodeOnPath])

            for pathIdx, edge in enumerate(outEdges):
                tempPathStrings = copy.deepcopy(pathStrings)
                # the source of the edge we knew
                curNode, outNode = edge
                # if we are not going on the path
                # This is adapted for being only one number ID
                if outNode not in path and outNode is not numberTokenIDs:
                    if sentenceDAG.node[outNode]["ner"] == "O":
                        if hasContentWord or sentenceDAG.node[outNode]["pos"][0] in "NVJR":
                            #print "*extend*" + sentenceDAG.node[outNode]["lemma"] + "~" + sentenceDAG[curNode][outNode]["label"]
                            #print pathStrings.insert(pathIdx, "*extend*" + sentenceDAG.node[outNode]["lemma"] + "~" + sentenceDAG[curNode][outNode]["label"])
                            tempPathStrings.insert(pathIdx, "*extend*" + sentenceDAG.node[outNode]["word"].lower() + "~" + sentenceDAG[curNode][outNode]["label"])
                            #print tempPathStrings
                            strings.append("+".join(tempPathStrings))
                    elif hasContentWord:
                        tempPathStrings.insert(pathIdx, "*extend*" + sentenceDAG.node[outNode]["ner"] + "~" + sentenceDAG[curNode][outNode]["label"])
                        strings.append("+".join(tempPathStrings))


#         # create additional paths by adding all out-edges from the number token (except for the one taking as back)
#         # the number token is the last one on the path
#         #outEdgesFromNumber = sentenceDAG.out_edges_iter([path[-1]])
#         #for edge in outEdgesFromNumber:
#             # the source of the edge we knew
#             dummy, outNode = edge
#             # if we are not going back
#             if outNode != path[-2] and outNode not in numberTokenIDs:
#                 if sentenceDAG.node[outNode]["ner"] == "O":
#                     if hasContentWord or  sentenceDAG.node[outNode]["pos"][0] in "NVJR":
#                         strings.append("+".join(pathStrings + ["NUMBER_SLOT~" + sentenceDAG[path[-1]][outNode]["label"] + "~" + sentenceDAG.node[outNode]["lemma"] ]))
#                 elif hasContentWord:
#                     strings.append("+".join(pathStrings + ["NUMBER_SLOT~" + sentenceDAG[path[-1]][outNode]["label"] + "~" + sentenceDAG.node[outNode]["ner"] ]))
#
#         # do the same for the LOCATION
#         outEdgesFromLocation = sentenceDAG.out_edges_iter([path[0]])
#         for edge in outEdgesFromLocation:
#             # the source of the edge we knew
#             dummy, outNode = edge
#             # if we are not going on the path
#             if outNode != path[1] and outNode not in locationTokenIDs:
#                 if sentenceDAG.node[outNode]["ner"] == "O":
#                     if hasContentWord or  sentenceDAG.node[outNode]["pos"][0] in "NVJR":
#                         strings.append("+".join([sentenceDAG.node[outNode]["lemma"] + "~"+ sentenceDAG[path[0]][outNode]["label"]] + pathStrings + ["NUMBER_SLOT"]))
#                 elif hasContentWord:
#                     strings.append("+".join([sentenceDAG.node[outNode]["ner"] + "~"+ sentenceDAG[path[0]][outNode]["label"]] + pathStrings + ["NUMBER_SLOT"]))
#

    return strings

def dictLocationMatching(sentence, tokenizedLocations):
    # first re-construct the sentence as a string
    wordsInSentence = []
    for token in sentence["tokens"]:
        wordsInSentence.append(token["word"])
    # print "Words in sentence are: " , wordsInSentence
    for tokLoc in tokenizedLocations:
        # print "Words in sentence are: " , wordsInSentence
        # print "Token location is: " , tokLoc
        tokenSeqs = [(i, i+len(tokLoc)) for i in range(len(wordsInSentence)) if wordsInSentence[i:i+len(tokLoc)] == tokLoc]
        # print "Token sequence is: " , tokenSeqs
        for tokenSeq in tokenSeqs:
            for tokenNo in range(tokenSeq[0], tokenSeq[1]):
                sentence["tokens"][tokenNo]["ner"]  = "LOCATION"

def getSurfacePatternsExtend(sentence, locationTokenIDs, numberTokenIDs, extend=True):
    # so this can go either from the location to the number, or the other way around
    # if the number token is before the first token of the location
    tokenSeqs = []
    if numberTokenIDs[-1] < locationTokenIDs[0]:
        tokenIDs = range(numberTokenIDs[-1]+1, locationTokenIDs[0])
    else:
        tokenIDs = range(locationTokenIDs[-1]+1, numberTokenIDs[0])

    # check whether there is a content word:
    hasContentWord = False
    tokens = []
    for id in tokenIDs:
        if sentence["tokens"][id]["ner"] == "O":
            tokens.append('"' + sentence["tokens"][id]["word"].lower() + '"')
            if sentence["tokens"][id]["pos"][0] in "NVJR":
                hasContentWord = True
        else:
            tokens.append('"' + sentence["tokens"][id]["ner"] + '"')

    if numberTokenIDs[-1] < locationTokenIDs[0]:
        tokens = ["NUMBER_SLOT"] + tokens + ["LOCATION_SLOT"]
    else:
        tokens = ["LOCATION_SLOT"] + tokens + ["NUMBER_SLOT"]
    if hasContentWord:
        tokenSeqs.append(tokens)

    if extend:
        lhsID = min(list(numberTokenIDs) + list(locationTokenIDs))
        rhsID = max(list(numberTokenIDs) + list(locationTokenIDs))
        # add the word to left
        extension = []
        extensionHasContentWord = False
        for idx in range(lhsID-1, max(-1, lhsID-10),-1):
            if sentence["tokens"][idx]["ner"] == "O":
                extension = ['"' + sentence["tokens"][idx]["word"].lower() + '"']  + extension
                if sentence["tokens"][idx]["pos"][0] in "NVJR":
                    extensionHasContentWord = True
            else:
                extension = ['"' + sentence["tokens"][idx]["ner"] + '"']  + extension
            # add the extension if it has a content word and the last thing added is not a comma
            if (hasContentWord or extensionHasContentWord) and (sentence["tokens"][idx]["word"] != ","):
                tokenSeqs.append(copy.copy(extension) + tokens)

        # and now to the right
        extension = []
        extensionHasContentWord = False
        for idx in range(rhsID+1, min(len(sentence["tokens"]), rhsID+9)):
            if sentence["tokens"][idx]["ner"] == "O":
                extension.append('"' + sentence["tokens"][idx]["word"].lower() + '"')
                if sentence["tokens"][idx]["pos"][0] in "NVJR":
                    extensionHasContentWord = True
            else:
                extension.append('"' + sentence["tokens"][idx]["ner"] + '"')
            # add the extension if it has a content word and the last thing added is not a comma
            if (hasContentWord or extensionHasContentWord) and (sentence["tokens"][idx]["word"] != ","):
                tokenSeqs.append(tokens + copy.copy(extension))

    return tokenSeqs

def getNumbers(sentence):
    # a number can span over multiple tokens
    tokenIDs2number = {}
    for idx, token in enumerate(sentence["tokens"]):
        # avoid only tokens known to be dates or part of locations
        # This only takes actual numbers into account thus it ignores things like "one million"
        # and also treating "500 millions" as "500"
        if token["ner"] not in ["DATE", "LOCATION", "PERSON", "ORGANIZATION", "MISC"]:
            try:
                # this makes sure that 123,123,123.23 which fails the float test, becomes 123123123.23 which is good
                tokenWithoutCommas = re.sub(",([0-9][0-9][0-9])", "\g<1>", token["word"])
                number = float(tokenWithoutCommas)
                # we want this to avoid taking in nan, inf and -inf as floats
                if numpy.isfinite(number):
                    ids = [idx]
                    # check the next token if it is million or thousand
                    if len(sentence["tokens"]) > idx+1:
                        if sentence["tokens"][idx+1]["word"].startswith("trillion"):
                            number = number * 1000000000000
                            ids.append(idx+1)
                            # print "Value extracted is: ", number
                        elif sentence["tokens"][idx+1]["word"].startswith("billion"):
                            number = number * 1000000000
                            ids.append(idx+1)
                            # print "Value extracted is: ", number
                        elif sentence["tokens"][idx+1]["word"].startswith("million"):
                            number = number * 1000000
                            ids.append(idx+1)
                            # print "Tokens of sentence are: ", sentence["tokens"]
                            # print "Value extracted is: ", number
                        elif sentence["tokens"][idx+1]["word"].startswith("thousand"):
                            number = number * 1000
                            ids.append(idx+1)
                            # print "Tokens of sentence are: ", sentence["tokens"]
                            # print "Value extracted is: ", number

                    tokenIDs2number[tuple(ids)] = number

            except ValueError:
                pass
    return tokenIDs2number


def getLocations(sentence):
    # note that a location can span multiple tokens
    tokenIDs2location = {}
    currentLocation = []
    for idx, token in enumerate(sentence["tokens"]):
        # if it is a location token add it:
        if token["ner"] == "LOCATION":
            currentLocation.append(idx)
        # if it is a no location token
        else:
            # check if we have just finished a location
            if len(currentLocation) > 0:
                # convert the tokenID to a tuple (immutable) and put the name there
                locationTokens = []
                for locIdx in currentLocation:
                    locationTokens.append(sentence["tokens"][locIdx]["word"])
                    # print "Location extracted is: ", sentence["tokens"][locIdx]["word"]

                tokenIDs2location[tuple(currentLocation)] = " ".join(locationTokens)
                currentLocation = []

    return tokenIDs2location


def buildDAGfromSentence(sentence):
    sentenceDAG = networkx.DiGraph()
    for idx, token in enumerate(sentence["tokens"]):
        sentenceDAG.add_node(idx, word=token["word"])
        sentenceDAG.add_node(idx, lemma=token["lemma"])
        sentenceDAG.add_node(idx, ner=token["ner"])
        sentenceDAG.add_node(idx, pos=token["pos"])

    # and now the edges:
    for dependency in sentence["dependencies"]:
        sentenceDAG.add_edge(dependency["head"], dependency["dep"], label=dependency["label"])
        # add the reverse if one doesn't exist
        # if an edge exists, the label gets updated, thus the standard edges do
        if not sentenceDAG.has_edge(dependency["dep"], dependency["head"]):
            sentenceDAG.add_edge(dependency["dep"], dependency["head"], label="-" + dependency["label"])
    return sentenceDAG


def fixSlots(oldTokens,locationTokenIDs,numberTokenIDs):

    token_by_index = dict(enumerate(oldTokens))
    groups = numberTokenIDs.keys() + locationTokenIDs.keys()
    for group in groups:
        token_by_index[group[0]] = ''.join(token_by_index.pop(index) for index in group)

    newTokens = [token for _, token in sorted(token_by_index.items(),key=lambda (index, _): index)]

    new_index_by_token = dict(map(lambda (i, t): (t, i), enumerate(newTokens)))
    newnumberTokenIDs = {(new_index_by_token[token_by_index[group[0]]],): value
                  for group, value in numberTokenIDs.items()}
    newlocationTokenIDs = {(new_index_by_token[token_by_index[group[0]]],): value
                    for group, value in locationTokenIDs.items()}

    # print "New Location token IDs are: ", newlocationTokenIDs
    # print "New Number token IDs are: ", newnumberTokenIDs
    # # # # # print "Location is: ", location
    # # # # # print "Number is: ", number
    # print "New Tokens are", newTokens

    return newTokens, newlocationTokenIDs,newnumberTokenIDs

if __name__ == "__main__":

    parsedJSONDir = sys.argv[1]

    labelFile = sys.argv[4]

    discardFile = sys.argv[5]

    wordDensityThreshold = float(sys.argv[6])

    # get all the files
    jsonFiles = glob.glob(parsedJSONDir + "/*.json")

    # one json to rule them all, the sentenceRegionValue.json
    outputFile = sys.argv[2]

    # this forms the columns using the lexicalized dependency and surface patterns
    pattern2location2values = {}

    sentences2location2values = {"sentences": []}

    sentences2location2valuesSlots = []

    sentences2location2valuesDiscarded = []

    print str(len(jsonFiles)) + " files to process"

    # load the hardcoded names (if any):
    tokenizedLocationNames = []
    if len(sys.argv) > 3:
        names = codecs.open(sys.argv[3], encoding='utf-8').readlines()
        for name in names:
            # print unicode(name).split()
            tokenizedLocationNames.append(unicode(name).split())
    # print "Dictionary with hardcoded tokenized location names"
    # print tokenizedLocationNames
    # Use len(jsonFiles) for all, 100 for testing
    for jsonFileName in itertools.islice(jsonFiles , 0, len(jsonFiles)):
    # for fileCounter, jsonFileName in enumerate(jsonFiles):
        # For each file in the HTML JSON
        print "processing " + jsonFileName
        with codecs.open(jsonFileName) as jsonFile:
            parsedSentences = json.loads(jsonFile.read())
        for sentence in parsedSentences:

            # print sentence

            #
            # fix the ner tags
            if len(tokenizedLocationNames)>0:
                dictLocationMatching(sentence, tokenizedLocationNames)
            tokenIDs2number = getNumbers(sentence)
            tokenIDs2location = getLocations(sentence)
            # if there was at least one location and one number build the dependency graph:
            # Check if len(sentence["tokens"])<120 step is valid

            if len(tokenIDs2number) > 0 and len(tokenIDs2location) > 0 and len(sentence["tokens"])<120:

                sentenceDAG = buildDAGfromSentence(sentence)

                # print "Dependencies are",sentenceDAG

                wordsInSentence = []

                for token in sentence["tokens"]:
                    wordsInSentence.append(token["word"])
                sample = " ".join(wordsInSentence)

                # print tokenIDs2number
                # print tokenIDs2location

                # print "Sentence is ",sample

                sampleTokens = sample.split()

                newTokens, newTokenIDs2location,newTokenIDs2number = fixSlots(sampleTokens,tokenIDs2location,tokenIDs2number)

                # cleanSample = " ".join(newTokens)

                for locationTokenIDs, location in newTokenIDs2location.items():
                    for numberTokenIDs, number in newTokenIDs2number.items():
                        # for locationTokenID in locationTokenIDs:
                        #     for numberTokenID in numberTokenIDs:
                            newTokens[numberTokenIDs[0]] = "NUMBER_SLOT"
                            newTokens[locationTokenIDs[0]] = "LOCATION_SLOT"

                for locationTokenIDs, location in tokenIDs2location.items():
                    for numberTokenIDs, number in tokenIDs2number.items():

                        sentenceDict = {}
        #
                        sentenceDict["sentence"] = sample
                        if len(tokenIDs2location)>3 or len(tokenIDs2number)>3:
                            sentenceDict["dense"]=True
                        else:
                            sentenceDict["dense"]=False

                        sentenceDict["location-value-pair"] = {location: number}

                        sampleTokens = sample.split()

                        for locationTokenID in locationTokenIDs:
                            sampleTokens[locationTokenID] = "LOCATION_SLOT"

                        for numberTokenID in numberTokenIDs:
                            sampleTokens[numberTokenID] = "NUMBER_SLOT"

                        slotSentence = (" ").join(sampleTokens)
                        sentenceDict["parsedSentence"] = slotSentence

                        sentenceDict["patterns"] = []

                        # for locationTokenID in locationTokenIDs:
                        #     for numberTokenID in numberTokenIDs:

                        shortestPaths = getShortestDepPaths(sentenceDAG, locationTokenIDs, numberTokenIDs)

                        patterns = []

                        for shortestPath in shortestPaths:
                            pathStrings = depPath2StringExtend(sentenceDAG, shortestPath, locationTokenIDs, numberTokenIDs)
                            patterns.extend(pathStrings)

                        # now get the surface strings
                        surfacePatternTokenSeqs = getSurfacePatternsExtend(sentence, locationTokenIDs, numberTokenIDs)
                        for surfacePatternTokens in surfacePatternTokenSeqs:
                            if len(surfacePatternTokens) < 15:
                                surfaceString = ",".join(surfacePatternTokens)
                                patterns.append(surfaceString)
                        # shortestPath = [val for sublist in shortestPaths for val in sublist]
                        # print "Shortest paths are",shortestPaths
                        sentenceDict["patterns"] = patterns

                        # ignore paths longer than some number deps (=tokens_on_path + 1)
                        if len(shortestPaths) > 0 and len(shortestPaths[0]) < 10:
                            for shortestPath in shortestPaths:
                                # print "Shortest path is",shortestPath
                                pathStrings = depPath2StringExtend(sentenceDAG, shortestPath, locationTokenIDs, numberTokenIDs)
                                # pathString = [val for sublist in pathStrings for val in sublist]

                                # print "Path strings are",pathStrings
                                if len(pathStrings) > 0:
                                    for i,pathString in enumerate(pathStrings):
                                        # print i
                                        text = [pathString]
                                        bigrams = [b for l in text for b in zip(l.split("+")[:-1], l.split("+")[1:])]
                                        # print "Bigrams are",bigrams
                                        # Note this just takes one of the bigrams which is the closest in terms of tokens
                                        sentenceDict["depPath"] = bigrams


                        fullSlotSentence = (" ").join(newTokens)
                        sentenceDict["slotSentence"] = fullSlotSentence
                        # print "Slot sentence is",fullSlotSentence
                        # print "Parsed sentence is",slotSentence,"\n"
                        sentences2location2values["sentences"].append(sentenceDict)
                        sentences2location2valuesSlots.append(sentenceDict)


    # Filtering the sentenceSlots afterwards

    result = []

    # TODO - need to also delete training instances with multiple region value-pairs, and do this for all countries
    for i,(sentence,finalSentence) in enumerate(zip(sentences2location2valuesSlots,sentences2location2values["sentences"])):
        fullSlotTokens = sentence['slotSentence'].split()
        # print "Slot is ",sentence['slotSentence']
        # print "Final sentence is",finalSentence
        sampleTokens = sentence['parsedSentence'].split()
        # print "Parsed sentence is",sentence['parsedSentence']
        # print "Old sample tokens are",sampleTokens,"\n"
        newTokens = []
        for i,token in enumerate(sampleTokens):
            if i>0 and ((token == "LOCATION_SLOT" and sampleTokens[i-1]=="LOCATION_SLOT") or (token == "NUMBER_SLOT" and sampleTokens[i-1]=="NUMBER_SLOT")):
                continue
            else:
                newTokens.append(token)

        sentence['parsedSentence']=(' ').join(newTokens)
        finalSentence['parsedSentence']=(' ').join(newTokens)

        # print "New sentence",sentence['parsedSentence'],"\n"

        locationCount=0
        numberCount=0

        # Remove items with too many location and number slots
        denseSentence = False
        tooManySlots = sentence["dense"]
        analyser = Text(fullSlotTokens)

        for token in fullSlotTokens:
            if token =="LOCATION_SLOT":
                locationCount+=1
            elif token =="NUMBER_SLOT":
                numberCount+=1
            if locationCount>3 or numberCount>3:
                # print "Too many tokens are",sampleTokens
                # print "Sentence is",sample
            # print "Number of locations", len(tokenIDs2location)
            # print "Number of values", len(tokenIDs2number)
                tooManySlots = True
                break
            wordDensity = float(analyser.count(token))/float(len(sampleTokens))
            # print wordDensity
            if wordDensity>wordDensityThreshold:
                # print "wordDensity is",wordDensity
                # print "threshold is",wordDensityThreshold
                # print "Too dense tokens are",sampleTokens
                # print "Sentence is",sample
                denseSentence = True
                # "Exiting loop..."
                break

        if tooManySlots or denseSentence:
            # print "Print true"
            # print "Dense sentence is",sentence["sentence"]
            sentences2location2valuesDiscarded.append(sentence)
        else:
            result.append(sentence)


    print "Model sentence length",len(sentences2location2values['sentences'])
    print "Labelled sentence length",len(result)
    print "Discarded sentence length",len(sentences2location2valuesDiscarded)

    with open(outputFile, "wb") as out:
        #Links the sentences to the region-value pairs
        json.dump(sentences2location2values, out,indent=4)

    with open(labelFile, "wb") as out:
        #Links the sentences to the region-value pairs
        json.dump(result, out,indent=4)

    with open(discardFile, "wb") as out:
        #Links the sentences to the region-value pairs
        json.dump(sentences2location2valuesDiscarded, out,indent=4)
