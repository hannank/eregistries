#!/usr/bin/env python3

import datetime
from dateutil.relativedelta import relativedelta
import requests
import json
import urllib.parse
import sys
import statistics

#
# Interpret the command line arguments
#
if len(sys.argv) < 5:
	print('Usage: python3 eregistries-analysis.py server username password orgUnitLevel')
	sys.exit(1)

api = sys.argv[1]
if api[-1] != '/':
	api += '/'
api += 'api/'
credentials = (sys.argv[2], sys.argv[3])
orgUnitLevel = sys.argv[4]

#
# Get the names of the three monthly periods for data to collect
#
today = datetime.date.today()
p1 = (today+relativedelta(months=-3)).strftime('%Y%m')
p2 = (today+relativedelta(months=-2)).strftime('%Y%m')
p3 = (today+relativedelta(months=-1)).strftime('%Y%m')

#
# Handy functions for accessing dhis 2
#
def d2get(args):
	# print(api + args)
	return requests.get(api + args, auth=credentials).json()

def d2post(args, data):
	# print(api + args, json.dumps(data))
	return requests.post(api + args, json=data, auth=credentials)

#
# Get a list of the facilities we will need with parents,
# and create a map from facilities to parents.
#	
facilities = d2get('organisationUnits.json?filter=level:eq:' + orgUnitLevel + '&fields=id,parent&paging=false')['organisationUnits']
parentMap = {}
for f in facilities:
	parentMap[f['id']] = f['parent']['id']

#
# Get a list of all indicators.
#
indicators = d2get('indicators.json?fields=id&paging=false')['indicators']

#
# Get the default categoryOptionCombo (which is also the default attributeOptionCombo)
#
defaultCoc = d2get('categoryOptionCombos.json?filter=name:eq:default')['categoryOptionCombos'][0]['id']

#
# Collect the input indicator data
# into nested dictionaries: parent . indicator . orgUnit . value array
#
input = {}
for i in indicators:
	if i['id'][0:4] == 'dash':
		result = d2get('analytics.json?dimension=dx:' + i['id'] + '&dimension=ou:GD7TowwI46c;LEVEL-' + orgUnitLevel + '&dimension=pe:' + p1 + ';' + p2 + ';' + p3 + '&skipMeta=true&includeNumDen=true')
		if 'rows' in result:
			for r in result['rows']:
				indicator = r[0]
				orgUnit = r[1]
				period = r[2]
				value = float( r[3] )
				denominator = r[5]
				if denominator:
					parent = parentMap[orgUnit]
					if not parent in input:
						input[parent] = {}
					if not indicator in input[parent]:
						input[parent][indicator] = {}
					if not orgUnit in input[parent][indicator]:
						input[parent][indicator][orgUnit] = []
					input[parent][indicator][orgUnit].append(value)
				else:
					print('Indicator ' + i['id'] + ' has some invalid data.')

#
# Construct a list of data values to output.
#
output = { 'dataValues': [] }

def putOut(orgUnit, dataElement, value):
	output['dataValues'].append( {
		'attributeOptionCombo': defaultCoc,
		'categoryOptionCombo': defaultCoc,
		'dataElement': dataElement,
		'orgUnit': orgUnit,
		'period': p3,
		'value': str( value )
		} )

for parent, indicators in input.items():
	for indicator, orgUnits in indicators.items():
		uidBase = 'de' + indicator[4:]
		averages = []
		for orgUnit, values in orgUnits.items():
			averages.append( int( round( statistics.mean( values ) ) ) )
		count = len( averages )
		for orgUnit, values in orgUnits.items():
			mean = int( round( statistics.mean( values ) ) )
			rank = float( sum( [ a <= mean for a in averages ] ) )
			percentile = int( round( 100 * rank / count ) )
			putOut( orgUnit, uidBase + 'Av', mean )
			putOut( orgUnit, uidBase + 'Q1', ( rank >= count * .25 ) - False )
			putOut( orgUnit, uidBase + 'Q2', ( rank >= count * .5 ) - False )
			putOut( orgUnit, uidBase + 'Q3', ( rank >= count * .75 ) - False )
			putOut( orgUnit, uidBase + 'DR', percentile )

#
# Import the output data into the DHIS 2 system.
#
print( 'Data post return status:', d2post( 'dataValueSets', output ) )
