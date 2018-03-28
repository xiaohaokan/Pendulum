import numpy as np
import copy
from keras.models import Sequential, load_model, clone_model
from keras.layers import Dense
from collections import deque


class QLearningModel(object):
    def __init__(self, inputs_n=3, neurons_n=(30, 14, 2), activations=("relu", "sigmoid", "linear")):
        """Конструктор"""
        self._inputs_n = inputs_n
        self._neurons_n = copy.copy(neurons_n)
        self._activations = copy.copy(activations)

        a_bound = 2  # Амплитуда управляющего сигнала
        self._alphabet = np.linspace(-a_bound, a_bound, neurons_n[-1])  # Алфавит действий
        self.max_replay_memory_size = 100000  # Максимальный размер истории опыта

        self.EPS_GREEDY = True  # Make random actions sometimes
        self.eps = 0.5  # Initial probability of random action
        self.EPS_DISCOUNT = 0.000008334  # By this value probability of random action is decreased by every step
        self.MIN_EPS = 0.05  # Minimum probability of random action
        self.BATCH_SIZE = 50  # Size of training batch on every step

        self.replay_memory = deque(maxlen=self.max_replay_memory_size)  # История опыта

        self.GAMMA = 0.85  # Discount factor

        self.neuralNet = Sequential()  # Нейронная сеть

        self.__new_nn(inputs_n, neurons_n, activations)

    def __new_nn(self, inputs_n, neurons_n, activations):
        """Создать новую нейронную сеть"""
        if type(inputs_n) != int:
            raise TypeError("inputs_n should be an integer")
        if inputs_n < 1:
            raise ValueError("inputs_n should be positive")
        if len(neurons_n) != len(activations):
            raise ValueError("neurons_n and activations should have the same length")
        del self.neuralNet
        self.replay_memory = deque(maxlen=self.max_replay_memory_size)
        self.neuralNet = Sequential()  # Нейронная сеть
        for i, (n, af) in enumerate(zip(neurons_n, activations)):  # Добавляем слои
            if i == 0:
                self.neuralNet.add(Dense(n, input_dim=inputs_n, kernel_initializer="normal", activation=af))
            else:
                self.neuralNet.add(Dense(n, kernel_initializer="normal", activation=af))
        self.neuralNet.compile(loss="mean_squared_error", optimizer="adam", metrics=["mae"])   # Компилируем сеть
        # Используется метод оптимизации Adam

    def reset_nn(self):
        """Создать новую нейронную сеть с исходными параметрами"""
        self.__new_nn(self._inputs_n, self._neurons_n, self._activations)

    def save_to_file(self, filename):
        """Сохранение сети вместе с весами в файл"""
        self.neuralNet.save(filename)

    def load_from_file(self, filename):
        """Загрузка сети вместе с весами из файла"""
        new_net = load_model(filename)
        if self.get_inputs_count(new_net) != self._inputs_n or self.get_outputs_count(new_net) != self._neurons_n[-1]:
            raise OSError("Unable to open file (wrong net configuration)")
        else:
            del self.neuralNet
            self.neuralNet = new_net
        return self

    def compute_batch(self, sa):
        """Обработка каждого элемента из массива"""
        return list(map(self.action_weights, self.neuralNet.predict(sa)))

    def compute(self, s):
        """Обработка одного элемента"""
        if type(s) != np.ndarray:
            raise TypeError("s should be a numpy array")
        if len(s) != self.get_inputs_count():
            raise ValueError("Length of s should be equal to number of inputs")
        # С вероятностью self.eps исследуем случайное действие
        rnd = np.random.sample()
        if rnd < self.eps and self.EPS_GREEDY:
            a = np.zeros_like(self._alphabet)
            a[np.random.randint(0, len(a))] = 1
        else:
            sa = np.array([s])
            qa = self.compute_batch(sa)
            a = qa[0]
        if self.eps > self.MIN_EPS:
            self.eps -= self.EPS_DISCOUNT  # Уменьшение вероятности случайного действия
        return sum(self._alphabet * a)

    @staticmethod
    def action_weights(q):
        """Вычисление вектора действия (one-hot-encoding) по вектору q-занчений"""
        if type(q) != np.ndarray:
            raise TypeError("q should be a numpy array")
        a = np.zeros_like(q)
        a[q.argmax()] = 1
        assert np.all(0 <= a)
        assert np.all(a <= 1)
        assert np.any(a > 0)
        assert a.sum() == 1
        return a

    def get_q(self, s):
        """Получить значения Q-функции для состояния s"""
        sa = np.array([s])
        qa = self.neuralNet.predict(sa)
        q = qa[0]
        return q

    def get_q_batch(self, s):
        """Получить значения Q-функции для каждого состояния из пачки s"""
        return self.neuralNet.predict(s)

    def training(self, s, a, r, s1):
        """
        Обучение нейронной сети.
        :param s: вектор предыдущего состояния
        :param a: действие
        :param r: скалярная награда, полученная при переходе из s в s1
        :param s1:  вектор нового состояния
        """
        if type(s) != np.ndarray:
            raise TypeError("s should be a numpy array")
        if type(r) == np.ndarray or type(r) == list or type(r) == tuple:
            raise TypeError("r should be a scalar")
        if type(s1) != np.ndarray:
            raise TypeError("s1 should be a numpy array")

        # Перевод действия в one-hot-encoding
        a_ohe = np.zeros_like(self._alphabet)
        a_ohe[self._alphabet == a] = 1
        self.replay_memory.append([s, a_ohe, r, s1])  # Добавление нового опыта в историю
        if len(self.replay_memory) < self.BATCH_SIZE:  # Если недостаточно опыта в истории, тренировки не происходит
            return

        batch_indexes = set()  # Случайные индексы элементов истории опыта
        batch_indexes.add(len(self.replay_memory)-1)
        while len(batch_indexes) < self.BATCH_SIZE:
            rnd = np.random.randint(0, len(self.replay_memory) - 1)
            batch_indexes.add(rnd)
        batch_indexes = list(batch_indexes)
        np.random.shuffle(batch_indexes)

        # Пачки векторов для тренировки
        sb = np.zeros((self.BATCH_SIZE, self.get_inputs_count()))
        ab = np.zeros((self.BATCH_SIZE, self.get_outputs_count()))
        rb = np.zeros((self.BATCH_SIZE, 1))
        s1b = np.zeros((self.BATCH_SIZE, self.get_inputs_count()))

        for i, index in enumerate(batch_indexes):
            sb[i, :] = self.replay_memory[index][0]
            ab[i, :] = self.replay_memory[index][1]
            rb[i, :] = self.replay_memory[index][2]
            s1b[i, :] = self.replay_memory[index][3]

        yb = self.__calc_target_batch(sb, ab, rb, s1b)
        self.neuralNet.fit(sb, yb, batch_size=self.BATCH_SIZE, epochs=1, shuffle=True, verbose=0)  # Обучение сети

    def get_inputs_count(self, net=None):
        """Количество входов сети"""
        if net is None:
            net = self.neuralNet
        cfg = net.get_config()
        return cfg[0]['config']['batch_input_shape'][1]

    def get_outputs_count(self, net=None):
        """Количество выходов сети"""
        if net is None:
            net = self.neuralNet
        cfg = net.get_config()
        return cfg[-1]['config']['units']

    def __calc_target(self, s, a, r, s1):
        """Вычисление данных, подаваемых на выход нейронной сети (согласно уравнению Беллмана)"""
        q = self.get_q(s)
        max_q1 = max(self.get_q(s1))
        alpha = 1
        return q + alpha * a * (r + self.GAMMA * max_q1 - q)

    def __calc_target_batch(self, s, a, r, s1):
        """Вычисление данных, подаваемых на выход нейронной сети (согласно уравнению Беллмана)"""
        Q = self.get_q_batch(s)
        max_Q1 = np.max(self.get_q_batch(s1), axis=1)
        max_Q1 = max_Q1.reshape((max_Q1.size,1))
        alpha = 1
        return Q + alpha * a * (r + self.GAMMA * max_Q1 - Q)
