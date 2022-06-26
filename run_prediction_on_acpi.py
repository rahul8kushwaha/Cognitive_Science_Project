"""Script which starts from timeseries extracted on ACPI.
   The timeseries are pre-extracted using several atlases
   AAL, Harvard Oxford, BASC, Power, MODL and can be downloaded from
   "https://osf.io/ab4q6/download"

   phenotypes: if not downloaded, it should be downloaded from
   https://s3.amazonaws.com/fcp-indi/data/Projects/ACPI/PhenotypicData/mta_1_phenotypic_data.csv

   Before, please read the data usage agreements and related material at
   http://fcon_1000.projects.nitrc.org/indi/ACPI/html/acpi_mta_1.html

   Prediction task is named as column "MJUser" and "SJTYP" is used as confounds
   regressing out on functional connectomes.

   After downloading, each folder should appear with name of the atlas and
   sub-folders, if necessary. For example, using BASC atlas, we have extracted
   timeseries signals with networks and regions. Regions implies while
   applying post-processing method to extract the biggest connected networks
   into separate regions. For MODL, we have extracted timeseries with
   dimensions 64 and 128 components.

   Dimensions of each atlas:
       AAL - 116
       BASC - 122
       Power - 264
       Harvard Oxford (cortical and sub-cortical) - 118
       MODL - 64 and 128

    The timeseries extraction process was done using Nilearn
    (http://nilearn.github.io/).

    Note: To run this script Nilearn is required to be installed.
"""
import os
import warnings
from os.path import join
import numpy as np
import pandas as pd

from downloader import fetch_acpi


def _get_paths(phenotypes, atlas, timeseries_dir):
    """
    """
    timeseries = []
    subject_ids = []
    mj_users = []
    sjtyps = []
    subids = phenotypes['SUBID']
    for index, subj_id in enumerate(subids):
        this_pheno = phenotypes[phenotypes['SUBID'] == subj_id]
        this_timeseries = join(timeseries_dir, atlas,
                               '00' + str(subj_id) + '-session_1' + '_timeseries.txt')
        if os.path.exists(this_timeseries):
            timeseries.append(np.loadtxt(this_timeseries))
            subject_ids.append(subj_id)
            mj_users.append(this_pheno['MJUser'].values[0])
            sjtyps.append(this_pheno['SJTYP'].values[0])
    return timeseries, mj_users, sjtyps, subject_ids


# Path to data directory where timeseries are downloaded. If not
# provided this script will automatically download timeseries in the
# current directory.

timeseries_dir = None

# If provided, then the directory should contain folders of each atlas name
if timeseries_dir is not None:
    if not os.path.exists(timeseries_dir):
        warnings.warn('The timeseries data directory you provided, could '
                      'not be located. Downloading in current directory.',
                      stacklevel=2)
        timeseries_dir = fetch_acpi(data_dir='./ACPI')
else:
    # Checks if there is such folder downloaded already in current
    # directory. Otherwise, downloads in current directory
    timeseries_dir = './ACPI'
    if not os.path.exists(timeseries_dir):
        timeseries_dir = fetch_acpi(data_dir='./ACPI')

# Path to data directory where predictions results should be
# saved.
predictions_dir = None

if predictions_dir is not None:
    if not os.path.exists(predictions_dir):
        os.makedirs(predictions_dir)
else:
    predictions_dir = './ACPI/predictions'
    if not os.path.exists(predictions_dir):
        os.makedirs(predictions_dir)

atlases = ['AAL', 'HarvardOxford', 'BASC/networks', 'BASC/regions',
           'Power', 'MODL/64', 'MODL/128']

dimensions = {'AAL': 116,
              'HarvardOxford': 118,
              'BASC/networks': 122,
              'BASC/regions': 122,
              'Power': 264,
              'MODL/64': 64,
              'MODL/128': 128}

# prepare dictionary for saving results
columns = ['atlas', 'measure', 'classifier', 'scores', 'iter_shuffle_split',
           'dataset', 'covariance_estimator', 'dimensionality']
results = dict()
for column_name in columns:
    results.setdefault(column_name, [])

# phenotypes
pheno_dir = 'mta_1_phenotypic_data.csv'
phenotypes = pd.read_csv(pheno_dir)

# Connectomes per measure
from connectome_matrices import ConnectivityMeasure
from sklearn.covariance import LedoitWolf
measures = ['correlation', 'partial correlation', 'tangent']

from my_estimators import sklearn_classifiers
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.model_selection import cross_val_score

cv = StratifiedShuffleSplit(n_splits=100, test_size=0.25,
                            random_state=0)

for atlas in atlases:
    print("Running predictions: with atlas: {0}".format(atlas))
    timeseries, mj_users, sjtyps, _ = _get_paths(phenotypes, atlas,
                                                 timeseries_dir)

    _, classes = np.unique(mj_users, return_inverse=True)
    iter_for_prediction = cv.split(timeseries, classes)

    for index, (train_index, test_index) in enumerate(iter_for_prediction):
        print("[Cross-validation] Running fold: {0}".format(index))
        for measure in measures:
            print("[Connectivity measure] kind='{0}'".format(measure))
            connections = ConnectivityMeasure(
                cov_estimator=LedoitWolf(assume_centered=True),
                kind=measure)
            conn_coefs = connections.fit_transform(timeseries,
                                                   confounds=np.array(sjtyps))

            for est_key in sklearn_classifiers.keys():
                print('Supervised learning: classification {0}'.format(est_key))
                estimator = sklearn_classifiers[est_key]
                score = cross_val_score(estimator, conn_coefs,
                                        classes, scoring='roc_auc',
                                        cv=[(train_index, test_index)])
                results['atlas'].append(atlas)
                results['iter_shuffle_split'].append(index)
                results['measure'].append(measure)
                results['classifier'].append(est_key)
                results['dataset'].append('ACPI')
                results['dimensionality'].append(dimensions[atlas])
                results['scores'].append(score)
                results['covariance_estimator'].append('LedoitWolf')
    res = pd.DataFrame(results)
    # save classification scores per atlas
    this_atlas_dir = join(predictions_dir, atlas)
    if not os.path.exists(this_atlas_dir):
        os.makedirs(this_atlas_dir)
    res.to_csv(join(this_atlas_dir, 'scores.csv'))
all_results = pd.DataFrame(results)
all_results.to_csv('predictions_on_acpi.csv')
