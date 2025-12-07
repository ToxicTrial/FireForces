import os
import random
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier

class MLModule:
    def __init__(self):
        self.regressor = RandomForestRegressor(n_estimators=50)
        self.classifier = RandomForestClassifier(n_estimators=50)
        self.is_trained = False
        self.data_path = "data/fires.csv"

    def load_or_generate_data(self):
        """
        Загружает CSV, если есть. Если нет - генерирует 'умные' синтетические данные.
        """
        if os.path.exists(self.data_path):
            print(f"Загрузка данных из {self.data_path}")
            df = pd.read_csv(self.data_path)
        else:
            print("Файл данных не найден. Генерация синтетического датасета...")
            os.makedirs("data", exist_ok=True)
            df = self.generate_realistic_data()
            df.to_csv(self.data_path, index=False)
            print(f"Датасет сохранен в {self.data_path}")
        
        return df

    def generate_realistic_data(self):
        """Создает данные с логическими зависимостями для обучения."""
        data = []
        for _ in range(500): # 500 сценариев
            area = random.randint(10, 800)       # Площадь
            units = random.randint(1, 15)        # Число пожарных
            intensity = random.randint(1, 5)     # Ранг пожара/Сложность
            
            # --- ФОРМУЛА ЛОГИКИ ---
            # Базовое время = (Площадь * Сложность) / Силы
            # Добавляем шум (случайные факторы)
            base_time = (area * intensity * 0.5) / (units + 0.5)
            time_loc = base_time + random.gauss(0, base_time * 0.1) # +/- 10% шума
            time_loc = max(1, time_loc) # Время не может быть отрицательным

            # Риск распространения: если сил мало на большую площадь
            risk_prob = (area * intensity) / (units * 100)
            risk = 1 if risk_prob > 1.2 else 0 # Класс 1 (Риск есть) или 0
            
            data.append([area, units, intensity, round(time_loc, 1), risk])
        
        return pd.DataFrame(data, columns=['area', 'units', 'intensity', 'time', 'risk'])

    def train(self):
        df = self.load_or_generate_data()
        
        X = df[['area', 'units', 'intensity']]
        y_time = df['time']
        y_risk = df['risk']
        
        self.regressor.fit(X, y_time)
        self.classifier.fit(X, y_risk)
        self.is_trained = True
        print("ML Модели успешно обучены.")

    def predict(self, area, units, intensity):
        if not self.is_trained:
            self.train()
        
        input_data = np.array([[area, units, intensity]])
        pred_time = self.regressor.predict(input_data)[0]
        pred_risk = self.classifier.predict(input_data)[0]
        
        return pred_time, pred_risk