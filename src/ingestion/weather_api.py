import openmeteo_requests
import pandas as pd
from retry_requests import retry
import requests_cache
from datetime import datetime, timedelta

cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

url_historic = "https://historical-forecast-api.open-meteo.com/v1/forecast"
params_historic = {
    "latitude": 47.1221,
    "longitude": 9.486,
    "start_date": "2022-01-01",
    "end_date": (datetime.now() - timedelta(1)).strftime("%Y-%m-%d"),
    "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
    "timezone": "Europe/Zurich",
}

url_now = "https://api.open-meteo.com/v1/forecast"
params_now = {
    "latitude": 47.1221,
    "longitude": 9.486,
    "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
    "models": "meteoswiss_icon_ch1",
    "timezone": "Europe/Zurich",
    "forecast_days": 2,  # index 0 = today, index 1 = tomorrow
}


def get_weather(url, params):
    responses = openmeteo.weather_api(url=url, params=params)
    response = responses[0]
    daily = response.Daily()

    daily_data = {
        "date": pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", utc=True),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left",
        ).tz_convert(response.Timezone().decode())
    }

    for i, var_name in enumerate(params["daily"]):
        daily_data[var_name] = daily.Variables(i).ValuesAsNumpy()

    forecast = pd.DataFrame(data=daily_data)

    return forecast


forecast_df = get_weather(url_now, params_now)
forecast_df["forecast_made_at"] = pd.Timestamp.now(tz="Europe/Zurich").normalize()
forecast_df["model"] = params_now["models"]

historic_df = get_weather(url_historic, params_historic)
historic_df["model"] = "best_match"
