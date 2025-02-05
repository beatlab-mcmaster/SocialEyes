#!/usr/bin/env python
import os

from setuptools import find_packages, setup

import versioneer

# Package meta-data.
NAME = "pl-rec-export"
DESCRIPTION = "Pupil Labs Recording Export Tool"
URL = "https://github.com/pupil-labs/pl-rec-export/"
EMAIL = "info@pupil-labs.com"
AUTHOR = "Pupil Labs GmbH"

here = os.path.abspath(os.path.dirname(__file__))

INSTALL_REQUIRES = [
    "av",
    "click",
    "click_aliases",
    "click_logging",
    "clickhouse_driver",
    "fs-s3fs",
    "intervaltree",
    "more_itertools",
    "natsort",
    "numpy",
    "requests",
    "mpmath",
    "pandas",
    "typeguard",
    "rich",
    "opencv-python-headless",
    "PyTurboJPEG",
    "xgboost==1.7.1",
    "diskcache",
    "sh",
    "tabulate",
    "semver",
    "scikit-learn",
    "tqdm",
    "pl-neon-recording"
]
TESTS_REQUIRE = ["pytest"]

here = os.path.abspath(os.path.dirname(__file__))

setup(
    name=NAME,
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description=DESCRIPTION,
    author=AUTHOR,
    author_email=EMAIL,
    url=URL,
    py_modules=[NAME],
    entry_points={
        "console_scripts": ["pl-rec-export = pupil_labs.rec_export.export:main"]
    },
    install_requires=INSTALL_REQUIRES,
    extras_require={
        "dev": [
            "pytest",
            "pytest-cov",
            "opencv-python-headless==4.6.0.66",
            "pytest-datadir",
            "bumpversion",
            "versioneer",
        ]
    },
    include_package_data=True,
    packages=find_packages("src"),
    package_dir={"": "src"},
    license="Proprietary",
)
