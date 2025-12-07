# train.py — Обучение классификатора и регрессора по данным FDNY

import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
from tqdm import tqdm
import time
import os

# Загрузка и подготовка данных
print("Загрузка данных...")
df = pd.read_csv("fdny_incidents.csv", low_memory=False)
df.columns = df.columns.str.lower()

columns = [
    'incident_date_time', 'arrival_date_time', 'borough_desc',
    'incident_type_desc', 'units_onscene', 'total_incident_duration'
]
df = df[columns].copy()

df.rename(columns={
    'incident_date_time': 'incident_time',
    'arrival_date_time': 'arrival_time',
    'borough_desc': 'borough',
    'incident_type_desc': 'incident_type',
    'units_onscene': 'units',
    'total_incident_duration': 'duration_sec'
}, inplace=True)

# Обработка дат
datetime_format = '%m/%d/%Y %I:%M:%S %p'
for col in ['incident_time', 'arrival_time']:
    df[col] = pd.to_datetime(df[col], format=datetime_format, errors='coerce')

# Очистка
df.dropna(subset=['incident_time', 'arrival_time', 'duration_sec'], inplace=True)
df = df[df['units'] > 0]
df['response_time'] = (df['arrival_time'] - df['incident_time']).dt.total_seconds()
df = df[(df['response_time'] >= 0) & (df['response_time'] < 3600)]

# Создание признаков
df['month'] = df['incident_time'].dt.month
df['hour'] = df['incident_time'].dt.hour
df['is_night'] = df['hour'].apply(lambda x: 1 if x < 6 or x >= 22 else 0)

le_borough = LabelEncoder()
le_type = LabelEncoder()
df['borough_enc'] = le_borough.fit_transform(df['borough'].astype(str))
df['type_enc'] = le_type.fit_transform(df['incident_type'].astype(str))

# Целевые переменные
df['delay_flag'] = (df['response_time'] > 300).astype(int)
features = ['borough_enc', 'type_enc', 'units', 'month', 'hour', 'is_night']
X = df[features]
y_class = df['delay_flag']
y_reg = df['response_time']

# Разделение на обучающую и тестовую выборки
print("Разделение данных...")
X_train_c, _, y_train_c, _ = train_test_split(X, y_class, test_size=0.2, random_state=42)
X_train_r, _, y_train_r, _ = train_test_split(X, y_reg, test_size=0.2, random_state=42)

# Обучение моделей
os.makedirs("models", exist_ok=True)

print("\nОбучение классификатора...")
tqdm_bar = tqdm(total=100, desc="Классификатор", ncols=100)
clf = RandomForestClassifier(n_estimators=100, random_state=42)
for _ in range(10):
    time.sleep(0.1)
    tqdm_bar.update(10)
clf.fit(X_train_c, y_train_c)
tqdm_bar.close()
joblib.dump(clf, "models/classifier.pkl")

print("\nОбучение регрессора...")
tqdm_bar = tqdm(total=100, desc="Регрессор", ncols=100)
reg = RandomForestRegressor(n_estimators=100, random_state=42)
for _ in range(10):
    time.sleep(0.1)
    tqdm_bar.update(10)
reg.fit(X_train_r, y_train_r)
tqdm_bar.close()
joblib.dump(reg, "models/regressor.pkl")

print("\n✅ Модели успешно обучены и сохранены в папку 'models/'")
