from time import time
from hashlib import sha256
from uuid import uuid4
from urllib.parse import urlparse
import json
import requests

from flask import Flask, jsonify, request


class Blockchain:
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()

        # Create the genesis block
        self.new_block(previous_hash=1, proof=100)

    def new_block(self, proof, previous_hash=None):
        """
        Creates a new Block and adds it to the Blockchain
        :param proof: <int> The proof given by the PoW algorithm
        :param previous_hash: (Optional) <str> The hash of the previous Block
        :return: The newly created Block
        """
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1])
        }

        self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """
        Creates a new transaction that will go into the next mined Block
        :param sender: <str> Address of the sender
        :param recipient: <str> Address of the recipient
        :param amount: <int> Amount sent
        :return: The index of the next Block that will be mined and will hold this transaction
        """

        self.current_transactions.append(
            {
                'sender': sender,
                'recipient': recipient,
                'amount': amount
            }
        )

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        """
        Creates a SHA256 hash of the Block
        :param block: <dict> The Block to be hashed
        :return: <str> The hash of the Block
        """
        block_string = json.dumps(block, sort_keys=True).encode()
        return sha256(block_string).hexdigest()

    @property
    def last_block(self):
        """
        :return: The last Block in the chain
        """
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        """
        Simple Proof of Work Algorithm:
         - Find a number p' such that hash(pp') contains leading 4 zeroes, where p is the previous p'
         - p is the previous proof, and p' is the new proof
        :param last_proof: <int>
        :return: <int>
        """
        proof = 0
        while not self.is_proof_valid(last_proof, proof):
            proof += 1

        return proof

    @staticmethod
    def is_proof_valid(last_proof, proof):
        """
        Validation function for our PoW algorithm
        :param last_proof: <int>
        :param proof: <int>
        :return: <bool>
        """
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def register_node(self, address):
        """
        Adds a new node to the nodes list
        :param address: <str> The address of the node
        :return: None
        """
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url)

    def valid_chain(self, chain):
        """
        Determine if the chain given is valid
        :param chain: <list> A Blockchain
        :return: <bool> True or False
        """
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            current_block = chain[current_index]
            if current_block['previous_hash'] != self.hash(last_block):
                return False

            if not self.is_proof_valid(last_block['proof'], current_block['proof']):
                return False

            last_block = current_block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        Consensus Algorithm which replaces the current node's chain with the longest in the network, thus resolving
        the conflicts
        :return: <bool> True or False
        """
        new_chain = None
        max_length = len(self.chain)

        for node in self.nodes:
            response = requests.get(f'http://{node}/chain')
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                if length > max_length:
                    max_length = length
                    new_chain = chain

        if new_chain:
            self.chain = new_chain
            return True

        return False


# Instantiate the Node
app = Flask(__name__)

# Generate a globally unique address for this Node
node_id = str(uuid4()).replace('-', '')

# Instantiate the Blockchain
blockchain = Blockchain()


@app.route('/mine', methods=['GET'])
def mine():
    blockchain.new_transaction(sender=0, recipient=node_id, amount=1)

    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': 'New Block forged',
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash']
    }
    return jsonify(response), 200


@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_data().decode()
    values = json.loads(values)

    required = ['sender', 'recipient', 'amount']
    if not all(val in values for val in required):
        return 'Missing values', 400

    index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {
        'message': f'Transaction will be added to the Block {index}'
    }
    return jsonify(response), 200


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'blockchain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_data().decode()
    values = json.loads(values)

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes)
    }
    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
