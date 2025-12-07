# Основной модуль системы анализа выездов (main.py)

import pandas as pd
import joblib
from sklearn.preprocessing import LabelEncoder

# Загрузка моделей
clf = joblib.load("models/classifier.pkl")
reg = joblib.load("models/regressor.pkl")

# Загрузка данных для анализа
print("Загрузка и подготовка данных...")
df = pd.read_csv("fdny_incidents.csv", low_memory=False)
df.columns = df.columns.str.lower()
df = df[['incident_date_time', 'borough_desc', 'incident_type_desc', 'units_onscene']].copy()
df.rename(columns={
    'incident_date_time': 'incident_time',
    'borough_desc': 'borough',
    'incident_type_desc': 'incident_type',
    'units_onscene': 'units'
}, inplace=True)

# Дата и признаки
datetime_format = '%m/%d/%Y %I:%M:%S %p'
df['incident_time'] = pd.to_datetime(df['incident_time'], format=datetime_format, errors='coerce')
df.dropna(subset=['incident_time', 'units'], inplace=True)
df = df[df['units'] > 0]
df['month'] = df['incident_time'].dt.month
df['hour'] = df['incident_time'].dt.hour
df['is_night'] = df['hour'].apply(lambda x: 1 if x < 6 or x >= 22 else 0)

# Кодирование
le_borough = LabelEncoder()
le_type = LabelEncoder()
df['borough_enc'] = le_borough.fit_transform(df['borough'].astype(str))
df['type_enc'] = le_type.fit_transform(df['incident_type'].astype(str))

# Подготовка признаков
features = ['borough_enc', 'type_enc', 'units', 'month', 'hour', 'is_night']
X = df[features]

# Предсказания
print("Выполняется предсказание...")
df['predicted_delay'] = clf.predict(X)
df['delay_proba'] = clf.predict_proba(X)[:, 1]
df['predicted_time_sec'] = reg.predict(X).round(0)

# Вывод результатов
print("\nПримеры анализа инцидентов:")
print(df[['incident_time', 'borough', 'incident_type', 'units', 'predicted_time_sec', 'predicted_delay', 'delay_proba']].head(10))