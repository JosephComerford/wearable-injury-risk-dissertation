# Can Wearable-Derived Health and Running Data Identify Patterns Associated with Injury Risk?

This repository contains the code developed for an MSc Data Science dissertation investigating whether wearable-derived health and running data can be used to identify patterns associated with injury risk.

## Project Overview

Wearable devices provide continuous information relating to training load, running mechanics, cardiovascular response, recovery and sleep. This project investigates whether patterns within these measurements can distinguish periods associated with injury from healthy periods.

The analysis uses 30-day samples of wearable-derived running and health data. Exploratory analysis, dimensionality reduction, clustering, anomaly detection and supervised classification are used to investigate patterns within the dataset.

## Data

The dataset contains wearable-derived running, health and recovery measurements.

Examples of variables used include:

- Running distance and frequency
- Ground contact time
- Cadence
- Running heart rate
- Running pace
- Stride length
- Resting heart rate
- Stress
- Heart rate variability (HRV)
- Sleep duration and sleep score
- Training-load-derived features

Each 30-day sample is labelled as either healthy or injured for the purposes of the analysis.

Raw datasets are not included in this repository because they contain participant-derived health and activity information.

## Methods

The project investigates the data using:

- Exploratory Data Analysis (EDA)
- Standardisation and preprocessing
- Principal Component Analysis (PCA)
- K-means clustering
- Anomaly detection
- Isolation Forest
- Logistic Regression
- Decision Tree
- AdaBoost
- Random Forest
- XGBoost

The analysis was primarily conducted using Python and Jupyter Notebook.

## Repository Structure

```text
wearable-injury-risk-dissertation/
│
├── data/
│   └── README.md
│
├── notebooks/
│   ├── 01_Single_Sample_EDA.ipynb
│   ├── 02_Anomaly_Detection.ipynb
│   ├── 03_Logistic_Regression.ipynb
│   ├── 04_Decision_Tree.ipynb
│   ├── 05_AdaBoost.ipynb
│   ├── 06_Random_Forest.ipynb
│   └── 07_XGBoost.ipynb
│
├── results/
│   └── figures/
│
├── src/
│   └── garmin_30_day_report.py
│
├── .gitignore
├── README.md
└── requirements.txt

## Data Files and Notebook Usage

Four datasets are supplied in the `data/` directory.

| Data file | Used by |
| --- | --- |
| `Report Sample 31 (Injured).csv` | `01_Single_Sample_EDA.ipynb` |
| `Report Sample 8 (Healthy).csv` | Optional alternative sample for `01_Single_Sample_EDA.ipynb` |
| `Combined Data VF.ods` | `02_Anomaly_Detection.ipynb` |
| `Trend Data Combined.ods` | `03_Logistic_Regression.ipynb`, `04_Decision_Tree.ipynb`, `05_AdaBoost.ipynb`, `06_Random_Forest.ipynb`, `07_XGBoost.ipynb` |

### Running the notebooks

The notebooks should be run in numerical order where practical.

`01_Single_Sample_EDA.ipynb` performs exploratory analysis on a single
30-day Garmin sample. It is configured to use the injured example,
`Report Sample 31 (Injured).csv`. To examine the supplied healthy example
instead, change the file path in the notebook to
`Report Sample 8 (Healthy).csv`.

`02_Anomaly_Detection.ipynb` uses the full daily time-series dataset
contained in `Combined Data VF.ods`.

Notebooks 03–07 use the processed sample-level dataset
`Trend Data Combined.ods` for supervised classification.

All required datasets are stored in the `data/` directory.