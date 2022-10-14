import json
import logging
import os
import sys
import time
from http import HTTPStatus

from logging.handlers import RotatingFileHandler
import requests
import telegram
from dotenv import load_dotenv

import exceptions

load_dotenv()


PRACTICUM_TOKEN = os.getenv('TOKEN_PRACT')
TELEGRAM_TOKEN = os.getenv('TOKEN_TG')
TELEGRAM_CHAT_ID = os.getenv('TG_CHAT_ID')


RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

VERDICT = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

# Временной диапазон всех работ
payload = {'from_date': 0}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='main.log',
    filemode='w')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler = logging.FileHandler('my_logger.log', 'w', 'utf-8')
handler.setFormatter(formatter)
logger.addHandler(handler)


def send_message(bot, message):
    """Отправляет сообщение."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info('Сообщение отправлено!')
    except telegram.error.TelegramError as error:
        logger.error(f'Ошибка: {error}')
        message = 'Ошибка отправки сообщения!'
        raise exceptions.NotSendMessageError(message)


def get_api_answer(current_timestamp):
    """Делает запрос к API."""
    timestamp = current_timestamp # or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != HTTPStatus.OK:
            message = 'Ошибка при получении ответа с сервера'
            raise exceptions.NonStatusCodeError(message)
        logger.info('Соединение с сервером установлено!')
        return response.json()
    except json.decoder.JSONDecodeError:
        raise exceptions.JSonDecoderError('Ошибка преобразования в JSON')
    except requests.RequestException as request_error:
        message = f'Код ответа API (RequestException): {request_error}'
        raise exceptions.WrongStatusCodeError(message)
    except ValueError as value_error:
        message = f'Код ответа API (ValueError): {value_error}'
        raise exceptions.WrongStatusCodeError(message)


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        logger.error('Ответ не является словарем')
        response = response[0]
    if 'homeworks' in response:
        homeworks = response['homeworks']
    else:
        logger.error('Отсутствует ключ homeworks')
        raise KeyError('Отсутствует ключ homeworks')
    if not isinstance(homeworks, list):
        logger.error('homeworks не является списком')
        raise exceptions.HomeworksIsListError('HomeworksIsListError')
    return homeworks


def parse_status(homework):
    """Извлекает статус работы и готовит строку из словаря."""
    # Извлекает название урока последней работы
    if not isinstance(homework, dict):
        try:
            homework = homework[0]
        except IndexError:
            logger.error('Список домашних работ пуст')
            raise IndexError('Список домашних работ пуст')
    homework_name = homework.get('homework_name')
    # Извлекает статус последней работы
    homework_status = homework.get('status')
    try:
        verdict = VERDICT[homework_status]
    except exceptions.UndifferentStatus as error:
        logger.error('Недокументированный статус домашней работы')
        message = f'Недокументированный статус домашней работы: {error}'
        raise exceptions.WrongStatusCodeError(message)
    # Возвращает строку для сообщения
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет наличие и корректность токенов."""
    if all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        return True


def main():
    """Основная логика работы бота."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    if check_tokens() is False:
        sys.exit(1)
    error_message = ''
    string = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            statuses = check_response(response)
            # Сравнивается статус, который был 10 минут назад
            # и новый статус, если !=, то отправляется сообщение
            if string != parse_status(statuses):
                string = parse_status(statuses)
                send_message(bot, string)
            time.sleep(RETRY_TIME)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(error)
            if message != error_message:
                send_message(bot, message)
                error_message = message
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
