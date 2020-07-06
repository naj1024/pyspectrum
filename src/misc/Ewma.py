"""
Exponentially Weighted Moving Average
"""


class Ewma:

    def __init__(self, alpha: float, initial=0.0):
        """
        An exponential weighted average with weight alpha
        Calculated as y(n) = a.x(n) + (1-a).y(n-1)
        :param alpha: The weight, range 0.0 to 1.0
        :param initial: The initial value
        """
        self._alpha = alpha
        self._ewma = initial

    def average(self, value: float) -> float:
        """
        Average the provided value
        :param value: The value
        :return: The average
        """
        self._ewma = self._alpha * value + (1 - self._alpha) * self._ewma
        return self._ewma

    def get_ewma(self) -> float:
        return self._ewma
