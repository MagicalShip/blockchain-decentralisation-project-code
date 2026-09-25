"""COMP 41770 - Worksheets 2 and 3: blocks, Merkle trees, and mining."""

import hashlib
import json
import time


# --- Task 1: transaction producer ---

class Transaction:
    def __init__(self, sender, receiver, amount):
        self.sender = sender
        self.receiver = receiver
        self.amount = amount

    def to_dict(self):
        return {"sender": self.sender, "receiver": self.receiver, "amount": self.amount}

    def __repr__(self):
        return f"Tx({self.sender}→{self.receiver}: {self.amount})"


class TransactionProducer:
    """Creates transactions and stores them to a file."""

    def __init__(self):
        self.transactions = []

    def create(self, sender, receiver, amount):
        tx = Transaction(sender, receiver, amount)
        self.transactions.append(tx)
        return tx

    def save(self, filename):
        with open(filename, "w") as f:
            json.dump([tx.to_dict() for tx in self.transactions], f, indent=2)


# --- Worksheet 3, Tasks 1 & 5: Merkle tree generation ---

def hash_transaction(transaction):
    """Return a repeatable SHA-256 hash for one transaction."""
    transaction_json = json.dumps(transaction.to_dict(), sort_keys=True)
    return hashlib.sha256(transaction_json.encode()).hexdigest()


def build_merkle_tree(transactions):
    """Build a Merkle tree for any non-empty transaction list, bottom-up."""
    if not transactions:
        raise ValueError("A Merkle tree requires at least one transaction")

    tree = [[hash_transaction(tx) for tx in transactions]]

    while len(tree[-1]) > 1:
        current_level = tree[-1]
        parent_level = []

        for i in range(0, len(current_level), 2):
            left_hash = current_level[i]
            if i + 1 < len(current_level):
                right_hash = current_level[i + 1]
            else:
                right_hash = left_hash

            combined_hashes = left_hash + right_hash
            parent_hash = hashlib.sha256(combined_hashes.encode()).hexdigest()
            parent_level.append(parent_hash)

        tree.append(parent_level)

    return tree


# --- Task 2 & 3: pending pool + block candidates ---

class TransactionPool:
    """Reads transactions from a file into a pool and picks block candidates."""

    def __init__(self):
        self.pending = []

    def load(self, filename):
        with open(filename) as f:
            self.pending = [Transaction(**d) for d in json.load(f)]

    def select_for_block(self, n):
        """Pick n transactions for a block, removing them from the pool."""
        picked, self.pending = self.pending[:n], self.pending[n:]
        return picked


# --- Worksheet 2, Task 4 + Worksheet 3, Task 2: blocks with Merkle trees ---

class Block:
    """A block holding transactions and its Merkle tree."""

    def __init__(self, transactions, previous_hash):
        self.timestamp = time.time()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.merkle_tree = build_merkle_tree(transactions)
        self.merkle_root = self.merkle_tree[-1][0]
        self.nonce = 0
        self.attempts = 0
        self.mining_time = 0.0
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        to_hash = (str(self.timestamp)
                   + self.merkle_root
                   + self.previous_hash
                   + str(self.nonce))
        return hashlib.sha256(to_hash.encode()).hexdigest()

    def mine(self, difficulty):
        """Change the nonce until the block hash has enough leading zeros."""
        if not isinstance(difficulty, int) or difficulty < 0:
            raise ValueError("difficulty must be a non-negative integer")

        target = "0" * difficulty
        self.nonce = 0
        self.attempts = 0
        start_time = time.perf_counter()

        while True:
            self.attempts += 1
            self.hash = self.calculate_hash()
            if self.hash.startswith(target):
                self.mining_time = time.perf_counter() - start_time
                return self.hash
            self.nonce += 1

    def __repr__(self):
        return (f"Block(txs={len(self.transactions)}, "
                f"nonce={self.nonce}, previous={self.previous_hash[:8]}…, "
                f"hash={self.hash[:8]}…)")


def is_valid_chain(blockchain):
    """True if every block's hash is correct and every link is intact."""
    for i, block in enumerate(blockchain):
        current_merkle_tree = build_merkle_tree(block.transactions)
        if block.merkle_tree != current_merkle_tree:
            return False
        if block.merkle_root != current_merkle_tree[-1][0]:
            return False
        if block.hash != block.calculate_hash():
            return False
        if i > 0 and block.previous_hash != blockchain[i - 1].hash:
            return False
    return True


def build_and_mine_chain(transaction_batches, difficulty):
    """Build a linked chain and mine every block at one difficulty."""
    chain = []
    previous_hash = "0" * 64

    for transactions in transaction_batches:
        block = Block(transactions, previous_hash)
        block.mine(difficulty)
        chain.append(block)
        previous_hash = block.hash

    return chain


def plot_mining_results(results, filename):
    """Plot mining time and attempts if matplotlib is available."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    figure, (time_plot, attempts_plot) = plt.subplots(2, 1, figsize=(10, 8))

    for difficulty, chain in results.items():
        block_numbers = range(1, len(chain) + 1)
        time_plot.plot(
            block_numbers,
            [block.mining_time for block in chain],
            marker="o",
            label=f"Difficulty {difficulty}",
        )
        attempts_plot.plot(
            block_numbers,
            [block.attempts for block in chain],
            marker="o",
            label=f"Difficulty {difficulty}",
        )

    time_plot.set_title("Mining time for each block")
    time_plot.set_xlabel("Block number")
    time_plot.set_ylabel("Time (seconds)")
    time_plot.legend()
    time_plot.grid(True)

    attempts_plot.set_title("Mining attempts for each block")
    attempts_plot.set_xlabel("Block number")
    attempts_plot.set_ylabel("Attempts")
    attempts_plot.legend()
    attempts_plot.grid(True)

    figure.tight_layout()
    figure.savefig(filename)
    plt.close(figure)
    return True


if __name__ == "__main__":
    # Worksheet 3, Task 2: produce 80 transactions and save them to a file.
    producer = TransactionProducer()
    for i in range(80):
        sender = f"User{i + 1}"
        receiver = f"User{(i + 1) % 80 + 1}"
        amount = i + 1
        producer.create(sender, receiver, amount)
    producer.save("transactions.json")

    # Load the 80 transactions into the pending pool.
    pool = TransactionPool()
    pool.load("transactions.json")
    print(f"pending: {len(pool.pending)} transactions")

    transaction_batches = [pool.select_for_block(8) for _ in range(10)]
    print(f"transactions left in pool: {len(pool.pending)}")

    # Worksheet 3, Task 4: compare time and attempts at several difficulties.
    results = {}
    for difficulty in (1, 2, 3, 4):
        chain = build_and_mine_chain(transaction_batches, difficulty)
        results[difficulty] = chain

        print(f"\nDifficulty {difficulty}")
        for block_number, block in enumerate(chain, start=1):
            print(f"Block {block_number}: time={block.mining_time:.6f}s, "
                  f"attempts={block.attempts}, nonce={block.nonce}")

        average_time = sum(block.mining_time for block in chain) / len(chain)
        average_attempts = sum(block.attempts for block in chain) / len(chain)
        print(f"Average: time={average_time:.6f}s, "
              f"attempts={average_attempts:.1f}")
        print(f"Valid chain: {is_valid_chain(chain)}")

    if plot_mining_results(results, "mining_results.png"):
        print("\nChart saved to mining_results.png")
    else:
        print("\nChart skipped: install matplotlib to create mining_results.png")

    # Tamper with a block and re-validate.
    chain = results[2]
    chain[1].transactions[0].amount = 999
    print(f"Valid after tampering: {is_valid_chain(chain)}")
