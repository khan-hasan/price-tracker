from configparser import ConfigParser 
from datetime import datetime
import json
import os
import time
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError
import boto3
from bs4 import BeautifulSoup
import jinja2
import requests


class Item:
    def __init__(self, sku: str, url: str, orig_price: float, current_price: float = None) -> None:
        self.name = None
        self.sku = sku
        self.url = url
        self.orig_price = orig_price
        self.current_price = None

        self.get_updated_info()

    def get_updated_info(self) -> None:
        response = requests.get(self.url)
        page_content = BeautifulSoup(response.text, 'html.parser')

        price = page_content.find_all('div', class_='price-tag')
        self.current_price = float(price[0].text.replace('$', ''))

        name = page_content.find_all('h2', class_='product-title')
        self.name = name[0].text


class Purchase:
    def __init__(self, items: List[Dict[str, float]], store_address: str, date: str, price_match_days: int = 60) -> None:
        self.items = self._make_item_list(items)
        self.date = date
        self.store_addr = store_address
        self.price_match_days = price_match_days

    def _make_item_list(self, items_dict: List[Dict[str, float]]) -> List[Item]:
        items = []
        for item in items_dict:
            sku = item.get('sku')
            orig_price = item.get('price')
            url = item.get('url')
            item = Item(sku=sku, url=url, orig_price=orig_price)
            items.append(item)
        return items


class ConfigReader:
    config_file = '.config.ini'

    def __init__(self, section: str = 'DEFAULT'):
        self.config_parser = ConfigParser()
        self.section = section

    def get_vars(self):
        self.config_parser.read(self.config_file)
        config_vars = {}
        for var, val in self.config_parser[self.section].items():
            config_vars[var] = val
        return config_vars


class EmailSender:
    charset = "UTF-8"

    def __init__(self, boto_session):
        self.boto_session = boto_session
        self.ses = self.boto_session.client('ses')
        self._template_name = 'email_template.html'

    def _load_template(self, content):
        templ_loader = jinja2.FileSystemLoader('templates')
        env = jinja2.Environment(loader=templ_loader)
        templ = env.get_template(self._template_name)
        return templ.render(items=content)

    def send(self, sender, recipients: List[str], subject: str, content: List[Any]):
        template = self._load_template(content)
        try:
            response = self.ses.send_email(
                Destination={
                    'ToAddresses': [
                        *recipients
                    ],
                },
                Message={
                    'Body': {
                        'Html': {
                            'Charset': self.charset,
                            'Data': template,
                        },
                    },
                    'Subject': {
                        'Charset': self.charset,
                        'Data': subject,
                    },
                },
                Source=sender
            )
        # Display an error if something goes wrong.
        except ClientError as e:
            print(e.response['Error']['Message'])
        else:
            print("Email sent! Message ID:"),
            print(response['MessageId'])


def lambda_handler(event, context):
    config_vars = ConfigReader().get_vars()
    aws_args = json.loads(config_vars.get('aws'))
    email_args = json.loads(config_vars.get('email'))
    purchase_args = json.loads(config_vars.get('purchase'))
    item_args = json.loads(config_vars.get('items'))

    purchase = Purchase(items=item_args, **purchase_args)

    boto_session = boto3.session.Session(**aws_args)
    email_sender = EmailSender(boto_session=boto_session)
    email_sender.send(content=purchase.items, **email_args)

    return {
        'statusCode': 200,
        'body': json.dumps('Completed Lambda execution.')
    }


if __name__ == '__main__':
    lambda_handler({}, {})
