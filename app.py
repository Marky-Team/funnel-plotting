# -*- coding: utf-8 -*-
"""funnel-plotting.py

## Funnel Analysis
[video walkthrough](https://www.loom.com/share/973078f6535b411496824e8219c2c437)
"""

import json
import streamlit as st
import os
import tempfile
from google.oauth2.service_account import Credentials
import gspread
import pandas as pd
from gspread_dataframe import get_as_dataframe
import plotly.express as px

st.set_page_config(layout="wide")


# AUTH
service_account_info = os.environ['SERVICE_CREDENTIALS']

service_account_info = json.loads(service_account_info)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
gc = gspread.authorize(creds)

# READ DATA
@st.cache_data
def load_data(sheet_name, worksheet_name):
    workbook = gc.open(sheet_name)
    worksheet = workbook.worksheet(worksheet_name)
    return get_as_dataframe(worksheet)

sheet_name = 'Funnel Analytics (2024 1/1-11/20)'
spend = load_data(sheet_name, "spend")
users = load_data(sheet_name, "users")
ads = load_data(sheet_name, "meta-ads-per-day")

for df in [spend, users, ads]:
  df.dropna(how='all', inplace=True)
  df.dropna(axis=1, how='all', inplace=True)

#@title User Funnel Data prep
users_cp = (
    users.assign(
        has_business=users['first_business'].notnull(),
        has_email=users['email'].notnull(),
        has_name=users['given_name'].notnull(),
        has_subscription=((users['subscription.subscription_id'].notna()) &
                          (users['subscription.is_appsumo'] == False)),
        created_at=pd.to_datetime(users['created_at'].apply(lambda x: x.split()[0]))
    )
    .set_index('created_at')
)
users_cp = users_cp[users_cp.index > '2024-01-01']

#@title Meta Ads Data Prep
ads_by_day = (
    ads
    .rename(columns={'Day': 'date'})
    .assign(date=lambda df: pd.to_datetime(df['date']))
    .set_index('date')
)

spend_cp = (
  spend
  .assign(date=lambda df: pd.to_datetime(spend.charge_date))
  .set_index('date')
  .resample('D').agg({
    'initial_spend': 'mean',
    'total_spend': 'mean',
  }))

merged_data = spend_cp.join(ads_by_day, how='inner')

# PLOT IT BABY!
st.title("Funnel Analysis")

grouping_period = st.selectbox("Select Grouping Period", ["daily", "weekly", "monthly"])
grouping_map = {
    "daily": "D",
    "weekly": "W-Mon",
    "monthly": "M",
}

user_data_to_plot = (users_cp
  .resample(grouping_map[grouping_period]).agg({
      # 'index': 'count',
      'has_business': 'mean',
      'has_post': 'mean',
      'has_email': 'mean',
      'has_name': 'mean',
      'has_subscription': 'mean'
  })
  .assign(pct_subscribed_x10=lambda df: df['has_subscription'] * 10)
  .rename(columns={
      'created_at': 'created',
      'has_business': 'pct_has_business',
      'has_post': 'pct_has_post',
      'has_email': 'pct_has_email',
      'has_name': 'pct_has_name',
      'has_subscription': 'pct_has_subscription'
  })[['pct_has_business', 'pct_has_post', 'pct_has_email', 'pct_has_name', 'pct_subscribed_x10']]
)


usd_data_to_plot = (
   merged_data
     .resample(grouping_map[grouping_period])
     .apply(lambda x: pd.Series({
        'Initial Spend': x['initial_spend'].mean(),
        'Customer Total Spend': x['total_spend'].mean(),
        'CAC': (x['Cost per purchase'] * x['Purchases']).sum() / x['Purchases'].sum(),
        'CPC': (x['CPC (cost per link click)'] * x['Link clicks']).sum() / x['Link clicks'].sum(),
        'Ad Spend': x['Amount spent (USD)'].sum(),
     }))
)

count_data_to_plot = (
   merged_data
     .resample(grouping_map[grouping_period])
     .apply(lambda x: pd.Series({
         'Purchases': x['Purchases'].sum(),
         'Clicks': x['Link clicks'].mean(),
     }))
)

# Figure 1: Users Created
users_created_fig = px.line(
    (users_cp
      .resample(grouping_map[grouping_period])
      .size().rename('Users Created')),
    labels={"index": "Date", "value": "Count"},
    title="Users Created",
    height=400,
)
users_created_fig.update_xaxes(title_text="")
st.plotly_chart(users_created_fig)

# Figure 2: User Funnel
user_funnel_fig = px.line(
    user_data_to_plot,
    labels={"index": "Date", "value": "Percentage"},
    title="User Funnel",
    height=400,
)
user_funnel_fig.update_xaxes(title_text="")
st.plotly_chart(user_funnel_fig)

# Figure 3: CAC vs Spend
cac_spend_fig = px.line(
    usd_data_to_plot,
    labels={'value': 'USD', 'date': 'Date'},
    title="CAC vs Spend",
    height=400,
)
cac_spend_fig.update_xaxes(title_text="")
st.plotly_chart(cac_spend_fig)

# Figure 4: Count Data
count_fig = px.line(
    count_data_to_plot,
    labels={'value': 'Count', 'date': 'Date'},
    title="Ad Count Data",
    height=400,
)
count_fig.update_xaxes(title_text="")
st.plotly_chart(count_fig)
