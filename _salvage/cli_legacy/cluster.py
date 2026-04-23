#-*- coding: utf-8 -*-
import json
import click
import os
import requests
from utils import get_header_basic_auth
from utils import API_URL_BASE, PUBLIC_KEY_PATH, KUBE_CONFIG_PATH
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP

import warnings as _warnings
import base64
import yaml
import subprocess as _subprocess
from tabulate import tabulate


@click.group()
def cluster():
    """The family commands to work with cluster"""
    pass


@cluster.command('list')
def list_clusters():
    url = '{}/clusters/list'.format(API_URL_BASE)
    headers = get_header_basic_auth()
    clusters = requests.get(url, headers=headers)
    clusters = json.loads(clusters.text)

    clusters_list = []
    for cluster in clusters["items"]:
        clusters_list.append([cluster['cluster_name'], cluster['cluster_alias']])
    print(tabulate(clusters_list, headers=["Name", "Alias"], tablefmt='orgtbl'))


@cluster.command('init')
@click.option('--cluster', 'cluster_name', prompt='Cluster name', help='The name of the cluster')
@click.option('--namespace', 'cluster_namespace', help='The name of the cluster')
def cluster_init(cluster_name, cluster_namespace=None):
    url = '{}/clusters/init'.format(API_URL_BASE)
    headers = get_header_basic_auth()

    body = {
        "cluster_name": cluster_name,
    }

    if cluster_namespace:
        body['cluster_namespace'] = cluster_namespace

    try:
        response = requests.put(url, headers=headers, json=body)
        # import pdb; pdb.set_trace()
        if response.status_code == 200:
            response_json = json.loads(response.text)
            print(response_json.get('message'))
        else:
            print('Unable to initialize cluster')
    except:
        print("Connection error")


@cluster.command()
@click.option('--config', prompt='Kubeconfig path', help='The path to the configuration file for kubernetes', type=click.Path(exists=True))
@click.option('--name', 'name', prompt='Cluster name', help='The name of the cluster')
@click.option('--alias', 'alias', prompt="Cluster alias", help='The alias of the cluster')
@click.option('--description', help='The description or purpose of the cluster')
def add(config, name, alias, description=""):
    """Creates a cluster for the account"""

    url = '{}/clusters/create'.format(API_URL_BASE)
    headers = get_header_basic_auth()

    body_cluster = {
        "cluster_name": name,
        "cluster_alias": alias,
        "cluster_description": description
    }

    response = requests.post(url, headers=headers, json=body_cluster)
    response_json = json.loads(response.text)

    if response.status_code != 201:
        print(response_json['message'])
        return

    check_for_pk()
    with open(PUBLIC_KEY_PATH, 'r') as public_key_file:
        public_key = public_key_file.read()
    with open(config, 'r') as kube_config:
        kube_config_file = kube_config.read()
    encrypted_config_file = encrypt_message(kube_config_file, public_key)
    # print (response_json["id_cluster"])
    # print(encrypted_config_file.decode("utf-8"))id_cluster
    upload_config_request_data = {
        "id_cluster": response_json["id_cluster"],
        "config": encrypted_config_file.decode("utf-8")
    }

    url = '{}/clusters/upload_config'.format(API_URL_BASE)
    updated = requests.put(url, headers=headers, json=upload_config_request_data)
    updated_json = json.loads(updated.text)
    if updated.status_code != 200:
        print(updated_json['message'])
        return

    print("Cluster created and config updated")




def check_for_pk():
    if not os.path.isfile(PUBLIC_KEY_PATH):
        print('Please login! Run \'dataspine login\'')


def encrypt_message(blob, public_key):
    rsa_key = RSA.importKey(public_key)
    rsa_key = PKCS1_OAEP.new(rsa_key)

    chunk_size = 470
    offset = 0
    end_loop = False
    encrypted = ""
    encrypted = bytes(encrypted.encode('utf-8'))

    try:
        while not end_loop:
            chunk = blob[offset:offset + chunk_size]

            if len(chunk) % chunk_size != 0:
                end_loop = True
                chunk += " " * (chunk_size - len(chunk))

            new_chunk = rsa_key.encrypt(bytes(chunk.encode('utf-8')))
            encrypted += new_chunk
            offset += chunk_size
    except:
        print("Encryption error")

    return base64.b64encode(encrypted)


def decrypt_blob(encrypted_blob, private_key):

    rsakey = RSA.importKey(private_key)
    rsakey = PKCS1_OAEP.new(rsakey)

    encrypted_blob = base64.b64decode(encrypted_blob)

    chunk_size = 512
    offset = 0
    decrypted = ""
    decrypted = bytes(decrypted.encode('utf-8'))

    while offset < len(encrypted_blob):
        chunk = encrypted_blob[offset: offset + chunk_size]
        new_chunk = rsakey.decrypt(chunk)
        decrypted += new_chunk
        offset += chunk_size

    return decrypted


def decrypt_message(encoded_encrypted_msg, privatekey):
    privatekey = RSA.importKey(privatekey)
    decoded_encrypted_msg = base64.b64decode(encoded_encrypted_msg)
    decoded_decrypted_msg = privatekey.decrypt(decoded_encrypted_msg)
    return decoded_decrypted_msg

