"""
Banking System Simulator
CIC-311 - Design and Analysis of Algorithms, mini project

    Need                              Data structure
    --------------------------------  ---------------------------------------
    Requests waiting to be served     LinkedQueue (FIFO, written from scratch)
    Recent activity of an account     HistoryStack (LIFO, one per account)
    Undo the latest transaction       bank-wide HistoryStack
    Find an account                   binary search on the sorted ledger
                                      (linear search and a dict-based hash
                                      lookup are kept for comparison)

Usage
    python start.py                 Parts B-D: dry run, rollback, searching
    python start.py --menu          ... then the interactive menu (Part E)
    python start.py --experiments   ... then benchmarks and charts (Part F, ~1 min)
    python start.py --all           everything
"""

import argparse
import itertools
from dataclasses import dataclass, field
from typing import List, Optional

LIMIT_PER_TXN = 200_000                       # largest single amount allowed
MIN_BAL = {"Savings": 500.0, "Current": 0.0}  # minimum balance by account type


class TransactionError(Exception):
    """A request that cannot be carried out (the reason is the message)."""


# ======================================================================
# Part A - Data structures and the simulator
# ======================================================================

# --------------------------------------------------------------- queue
class _QNode:
    __slots__ = ("item", "next")

    def __init__(self, item):
        self.item, self.next = item, None


class LinkedQueue:
    """Singly linked list with head (front) and tail (rear) pointers.
    enqueue at the tail and dequeue at the head are both O(1)."""

    def __init__(self):
        self.head = self.tail = None
        self.count = 0

    def enqueue(self, item):
        node = _QNode(item)
        if self.tail is None:            # empty queue
            self.head = self.tail = node
        else:
            self.tail.next = node
            self.tail = node
        self.count += 1

    def dequeue(self):
        if self.head is None:
            raise IndexError("queue underflow")
        node = self.head
        self.head = node.next
        if self.head is None:            # queue became empty
            self.tail = None
        self.count -= 1
        return node.item

    def front(self):
        return None if self.head is None else self.head.item

    def empty(self):
        return self.count == 0

    def __len__(self):
        return self.count

    def __iter__(self):
        cur = self.head
        while cur:
            yield cur.item
            cur = cur.next


# --------------------------------------------------------------- stack
class HistoryStack:
    """Array-based stack. push / pop / peek are O(1); latest(k) is O(k)."""

    def __init__(self):
        self.data = []

    def push(self, item):
        self.data.append(item)

    def pop(self):
        if not self.data:
            raise IndexError("stack underflow")
        return self.data.pop()

    def peek(self):
        return self.data[-1] if self.data else None

    def empty(self):
        return len(self.data) == 0

    def __len__(self):
        return len(self.data)

    def latest(self, k):
        """k most recent entries, newest first, without removing them."""
        top = len(self.data) - 1
        return [self.data[top - i] for i in range(min(k, len(self.data)))]


# --------------------------------------------------------------- records
@dataclass
class Account:
    number: int
    holder: str
    kind: str                 # "Savings" or "Current"
    balance: float
    activity: HistoryStack = field(default_factory=HistoryStack, repr=False)


_txn_counter = itertools.count(1)


@dataclass
class Txn:
    op: str                   # "deposit", "withdraw" or "transfer"
    source: int
    amount: float
    dest: Optional[int] = None
    day: int = 1
    tid: int = field(default_factory=lambda: next(_txn_counter))
    state: str = "QUEUED"     # QUEUED -> DONE / REJECTED -> ROLLED BACK
    note: str = ""
    closing: Optional[float] = None   # source balance after the transaction

    def describe(self):
        to = f" to {self.dest}" if self.dest else ""
        return f"#{self.tid} {self.op} {self.source}{to} Rs {self.amount:,.0f}"


# --------------------------------------------------------------- bank
class BankSimulator:
    def __init__(self, first_number=81001):
        self.ledger: List[Account] = []     # sorted by account number
        self.lookup = {}                    # number -> Account (hash table)
        self.pending = LinkedQueue()        # requests waiting to be served
        self.rollback = HistoryStack()      # successful txns, newest on top
        self.journal: List[Txn] = []        # every served request
        self.next_number = first_number

    # ---------------------------------------------------- accounts
    def create_account(self, holder, kind="Savings", opening=0.0):
        if kind not in MIN_BAL:
            raise TransactionError(f"Unknown account type '{kind}'")
        if opening < MIN_BAL[kind]:
            raise TransactionError(f"Opening balance must be at least Rs {MIN_BAL[kind]:,.0f}")
        acc = Account(self.next_number, holder, kind, float(opening))
        self.next_number += 1
        self.ledger.append(acc)     # numbers only increase -> ledger stays sorted
        self.lookup[acc.number] = acc
        return acc.number

    # ---------------------------------------------------- searching
    def find_linear(self, number):
        steps = 0
        for acc in self.ledger:
            steps += 1
            if acc.number == number:
                return acc, steps
        return None, steps

    def find_binary(self, number, log=None):
        low, high, steps = 0, len(self.ledger) - 1, 0
        while low <= high:
            mid = (low + high) // 2
            steps += 1
            here = self.ledger[mid].number
            if log is not None:
                log.append((steps, low, high, mid, here))
            if here == number:
                return self.ledger[mid], steps
            if here < number:
                low = mid + 1
            else:
                high = mid - 1
        return None, steps

    def find_hash(self, number):
        return self.lookup.get(number), 1

    def find_by_name(self, part):
        part = part.lower()
        return [a for a in self.ledger if part in a.holder.lower()]

    def account(self, number):
        acc, _ = self.find_binary(number)
        if acc is None:
            raise TransactionError(f"No account numbered {number}")
        return acc

    # ---------------------------------------------------- requests
    def request(self, op, source, amount, dest=None, day=1):
        t = Txn(op, source, amount, dest, day)
        self.pending.enqueue(t)
        return t

    def _check_and_apply(self, t):
        if t.op not in ("deposit", "withdraw", "transfer"):
            raise TransactionError(f"Unknown operation '{t.op}'")
        if t.amount <= 0 or t.amount > LIMIT_PER_TXN:
            raise TransactionError(f"Amount Rs {t.amount:,.2f} is outside the allowed range")
        src = self.account(t.source)
        if t.op == "deposit":
            src.balance += t.amount
            src.activity.push(t)
        else:
            if src.balance - t.amount < MIN_BAL[src.kind]:
                raise TransactionError(f"Not enough balance (Rs {src.balance:,.2f})")
            if t.op == "transfer":
                if t.dest == t.source:
                    raise TransactionError("Source and destination are the same")
                dst = self.account(t.dest)       # checked before any money moves
                dst.balance += t.amount
                dst.activity.push(t)
            src.balance -= t.amount
            src.activity.push(t)
        t.closing = src.balance

    def serve_next(self):
        t = self.pending.dequeue()
        try:
            self._check_and_apply(t)
        except TransactionError as err:
            t.state, t.note = "REJECTED", str(err)
        else:
            t.state, t.note = "DONE", "OK"
            self.rollback.push(t)
        self.journal.append(t)
        return t

    def serve_all(self):
        served = []
        while not self.pending.empty():
            served.append(self.serve_next())
        return served

    # ---------------------------------------------------- history / rollback
    def mini_statement(self, number, k=5):
        return self.account(number).activity.latest(k)

    def rollback_last(self):
        if self.rollback.empty():
            raise TransactionError("No transaction left to roll back")
        t = self.rollback.pop()
        src = self.account(t.source)
        if t.op == "deposit":
            src.balance -= t.amount
        elif t.op == "withdraw":
            src.balance += t.amount
        else:
            dst = self.account(t.dest)
            dst.balance -= t.amount
            src.balance += t.amount
            dst.activity.pop()
        src.activity.pop()      # t is on top: every later txn was already rolled back
        t.state, t.note = "ROLLED BACK", "Reversed by bank"
        return t

    def total_money(self):
        return sum(a.balance for a in self.ledger)


def rupees(x):
    return f"Rs {x:,.2f}"


# ======================================================================
# Shared demo data
# ======================================================================
DEMO_ACCOUNTS = [("Priya Menon", "Savings", 18000), ("Arjun Reddy", "Current", 52000),
                 ("Sana Qureshi", "Savings", 6500), ("Karan Malhotra", "Savings", 21000),
                 ("Nisha Pillai", "Current", 35000), ("Rahul Bose", "Savings", 2000),
                 ("Tanvi Kulkarni", "Savings", 9500), ("Dev Chopra", "Current", 14000)]

DEMO_REQUESTS = [("deposit", 81003, 4000, None), ("transfer", 81002, 12000, 81001),
                 ("withdraw", 81006, 1800, None), ("withdraw", 81001, 8000, None),
                 ("deposit", 81012, 2000, None), ("transfer", 81005, 6000, 81007),
                 ("withdraw", 81004, 250000, None), ("transfer", 81008, 3000, 81008),
                 ("deposit", 81006, 1500, None), ("withdraw", 81007, 10000, None),
                 ("transfer", 81001, 2500, 81006), ("withdraw", 81002, 5000, None)]


def heading(text):
    print("\n" + "=" * 72 + f"\n{text}\n" + "=" * 72)


def show(rows, columns):
    """Print a table; uses pandas when available, plain text otherwise."""
    try:
        import pandas as pd
        print(pd.DataFrame(rows, columns=columns).to_string(index=False))
    except ImportError:
        widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) for i, c in enumerate(columns)]
        print("  ".join(str(c).ljust(w) for c, w in zip(columns, widths)))
        for r in rows:
            print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))


def show_ledger(bank):
    show([[a.number, a.holder, a.kind, a.balance] for a in bank.ledger],
         ["number", "holder", "kind", "balance"])


# ======================================================================
# Part B - Dry run: 8 accounts, 12 queued requests
# ======================================================================
def part_b():
    heading("Part B - Dry run: 8 accounts, 12 queued requests")
    bank = BankSimulator()
    for holder, kind, opening in DEMO_ACCOUNTS:
        bank.create_account(holder, kind, opening)
    for op, src, amt, dst in DEMO_REQUESTS:
        bank.request(op, src, amt, dst)

    print("Waiting in the queue (front first):")
    for t in bank.pending:
        print("   ", t.describe())

    log = []
    while not bank.pending.empty():
        t = bank.serve_next()
        log.append([t.tid, t.op, t.source, t.dest or "-", t.amount, t.state,
                    rupees(t.closing) if t.state == "DONE" else t.note, len(bank.pending)])
    print()
    show(log, ["Txn", "Operation", "Source", "Destination", "Amount",
               "Result", "Balance / reason", "Still queued"])
    print()
    show_ledger(bank)
    return bank


# ======================================================================
# Part C - Activity stack (mini statement) and rollback
# ======================================================================
def part_c(bank):
    heading("Part C - Activity stack (mini statement) and rollback")
    print("Mini statement of 81001 (newest first):")
    for t in bank.mini_statement(81001, 5):
        print("   ", t.describe())
    print()
    for _ in range(2):
        t = bank.rollback_last()
        print(f"Rolled back {t.describe()}  ->  rollback stack now holds {len(bank.rollback)}")
    print()
    show_ledger(bank)


# ======================================================================
# Part D - Searching for an account
# ======================================================================
def part_d(bank):
    heading("Part D - Searching for an account")
    ledger = BankSimulator()
    for i in range(2000):
        ledger.create_account(f"Holder {i}", "Savings", 1000)

    trace = []
    acc, steps = ledger.find_binary(82487, log=trace)
    show(trace, ["Step", "LOW", "HIGH", "MID", "L[MID].number"])
    print(f"\nbinary search: found {acc.number} after {steps} comparisons")
    print(f"linear search: {ledger.find_linear(82487)[1]} comparisons")
    print("hash lookup  :", ledger.find_hash(82487)[0])
    print("names containing 'ra':", [(a.number, a.holder) for a in bank.find_by_name("ra")])


# ======================================================================
# Part E - Try it yourself
# ======================================================================
MENU = """
 a) open account      b) deposit        c) withdraw       d) transfer
 e) serve the queue   f) find by number g) find by name   h) mini statement
 i) roll back last    q) quit"""


def run_menu(bank):
    heading("Part E - Try it yourself")
    while True:
        print(MENU)
        try:
            choice = input("choice> ").strip().lower()
        except EOFError:
            break
        try:
            if choice == "a":
                n = bank.create_account(input("holder: "), input("Savings/Current: ").strip().title(),
                                        float(input("opening amount: ")))
                print("new account", n)
            elif choice in ("b", "c"):
                op = "deposit" if choice == "b" else "withdraw"
                t = bank.request(op, int(input("account: ")), float(input("amount: ")))
                print("queued", t.describe(), "| waiting:", len(bank.pending))
            elif choice == "d":
                t = bank.request("transfer", int(input("from: ")), float(input("amount: ")), int(input("to: ")))
                print("queued", t.describe(), "| waiting:", len(bank.pending))
            elif choice == "e":
                for t in bank.serve_all():
                    print(f"   {t.describe():42s} {t.state:9s} {t.note}")
            elif choice == "f":
                acc, steps = bank.find_binary(int(input("account: ")))
                print(acc if acc else "not found", f"[{steps} comparisons]")
            elif choice == "g":
                for a in bank.find_by_name(input("name contains: ")):
                    print("  ", a)
            elif choice == "h":
                for t in bank.mini_statement(int(input("account: ")), 5):
                    print("  ", t.describe())
            elif choice == "i":
                print("rolled back", bank.rollback_last().describe())
            elif choice == "q":
                break
            else:
                print("!! unknown choice")
        except (TransactionError, ValueError) as e:
            print("!!", e)


# ======================================================================
# Part F - Experiments and charts
# ======================================================================
FIRST = ["Priya", "Arjun", "Sana", "Karan", "Nisha", "Rahul", "Tanvi", "Dev", "Isha", "Yash", "Pooja",
         "Nikhil", "Zoya", "Harsh", "Kavya", "Manav", "Riya", "Sahil", "Anjali", "Varun"]
LAST = ["Menon", "Reddy", "Qureshi", "Malhotra", "Pillai", "Bose", "Kulkarni", "Chopra", "Agarwal",
        "Fernandes", "Saxena", "Bhat", "Ghosh", "Patel"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def make_bank(n, seed):
    import random
    rng = random.Random(seed)
    b = BankSimulator()
    for _ in range(n):
        kind = "Current" if rng.random() < 0.3 else "Savings"
        b.create_account(f"{rng.choice(FIRST)} {rng.choice(LAST)}", kind, round(rng.uniform(800, 120000), 2))
    return b


def flood(b, m, seed, days=6, junk=0.04):
    import random
    rng = random.Random(seed)
    lo, hi = b.ledger[0].number, b.ledger[-1].number
    for i in range(m):
        src = rng.randint(lo, hi)
        amt = round(rng.uniform(200, 6000) if rng.random() < 0.6 else rng.uniform(6000, 60000), 2)
        u = rng.random()
        if u < junk / 2:
            src = hi + rng.randint(1, 5000)                    # account that does not exist
        elif u < junk:
            amt = rng.choice([0.0, -750.0, 450000.0])         # amount outside the allowed range
        op = rng.choices(["deposit", "withdraw", "transfer"], [0.42, 0.40, 0.18])[0]
        b.request(op, src, amt, rng.randint(lo, hi) if op == "transfer" else None, 1 + i * days // m)


class LinearLookupBank(BankSimulator):
    """Same bank, but the queue server finds accounts with linear search."""

    def account(self, number):
        acc, _ = self.find_linear(number)
        if acc is None:
            raise TransactionError(f"No account numbered {number}")
        return acc


def bank_day(counters, rate=2.2, minutes=420, seed=9):
    """Waiting line over one working day with `counters` tellers."""
    import numpy as np
    rng = np.random.default_rng(seed)
    line, waits, length = LinkedQueue(), [], []
    arrivals = rng.poisson(rate, minutes)
    for minute in range(minutes):
        for _ in range(arrivals[minute]):
            line.enqueue(minute)
        for _ in range(counters):
            if not line.empty():
                waits.append(minute - line.dequeue())
        length.append(len(line))
    return {"length": length, "arrived": int(arrivals.sum()), "served": len(waits), "left": len(line),
            "avg_wait": float(np.mean(waits)), "p90_wait": float(np.percentile(waits, 90)),
            "peak": int(max(length))}


def run_experiments(chart_dir="charts"):
    """Runs every test / benchmark used in the report and draws the charts."""
    import gc, json, os, random, textwrap, time
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mtick
    import seaborn as sns

    heading("Part F - Experiments and charts (about a minute)")
    os.makedirs(chart_dir, exist_ok=True)
    VIOLET, AMBER, AQUA, INK, SOFT = "#6250d6", "#eda100", "#1baf7a", "#1d1d1b", "#6b6a66"
    sns.set_theme(style="ticks", font="DejaVu Sans", rc={
        "axes.edgecolor": SOFT, "axes.labelcolor": INK, "xtick.color": SOFT, "ytick.color": SOFT,
        "axes.titleweight": "bold", "axes.titlesize": 10.5, "axes.labelsize": 9.5, "font.size": 9,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#ebeae6", "grid.linewidth": 0.7,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})
    random.seed(2026); np.random.seed(2026)
    R = {}

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(os.path.join(chart_dir, f"{name}.png"), dpi=200)
        plt.close(fig)

    # -------------------------------------------------------------- A. demo run
    demo = BankSimulator()
    for holder, kind, opening in DEMO_ACCOUNTS:
        demo.create_account(holder, kind, opening)
    R["demo_open"] = [[a.number, a.holder, a.kind, a.balance] for a in demo.ledger]
    for op, s, amt, d in DEMO_REQUESTS:
        demo.request(op, s, amt, d)
    R["demo_queue"] = [t.describe() for t in demo.pending]
    rows = []
    while not demo.pending.empty():
        t = demo.serve_next()
        rows.append([f"#{t.tid}", t.op.capitalize(), str(t.source) + (f" → {t.dest}" if t.dest else ""),
                     f"{t.amount:,.0f}", "Done" if t.state == "DONE" else "Rejected",
                     rupees(t.closing) if t.state == "DONE" else t.note, len(demo.pending)])
    R["demo_trace"] = rows
    R["demo_close"] = [[a.number, a.holder, a.kind, a.balance] for a in demo.ledger]
    flows = []
    for a in demo.ledger:
        inn = sum(t.amount for t in demo.journal if t.state == "DONE" and
                  ((t.op == "deposit" and t.source == a.number) or (t.op == "transfer" and t.dest == a.number)))
        out = sum(t.amount for t in demo.journal if t.state == "DONE" and t.op in ("withdraw", "transfer")
                  and t.source == a.number)
        flows.append([a.holder, inn, out])
    R["demo_flows"] = flows
    R["stmt_81001"] = [[f"#{t.tid}", t.op.capitalize(), f"{t.amount:,.0f}",
                        f"from {t.source}" if t.dest == 81001 else (f"to {t.dest}" if t.dest else "—")]
                       for t in demo.mini_statement(81001, 5)]
    R["stmt_81006"] = [[f"#{t.tid}", t.op.capitalize(), f"{t.amount:,.0f}"] for t in demo.mini_statement(81006, 5)]
    rb = []
    for _ in range(2):
        t = demo.rollback_last()
        touched = [t.source] + ([t.dest] if t.dest else [])
        rb.append([f"#{t.tid}", t.op.capitalize(), f"{t.amount:,.0f}",
                   "; ".join(f"{n} → {rupees(demo.account(n).balance)}" for n in touched), len(demo.rollback)])
    R["demo_rollback"] = rb
    R["name_search"] = [[a.number, a.holder] for a in demo.find_by_name("ra")]

    big = BankSimulator(first_number=81001)
    for i in range(2000):
        big.create_account(f"Holder {i}", "Savings", 1000)
    log = []
    big.find_binary(82487, log=log)
    R["bsearch_log"] = log
    R["bsearch_linear_steps"] = big.find_linear(82487)[1]

    # -------------------------------------------------------------- B. bulk simulation
    sim = make_bank(2000, 11)
    opening = {a.number: a.balance for a in sim.ledger}
    open_total = sim.total_money()
    flood(sim, 60000, 12)
    sim.serve_all()
    done = [t for t in sim.journal if t.state == "DONE"]
    dep = sum(t.amount for t in done if t.op == "deposit")
    wd = sum(t.amount for t in done if t.op == "withdraw")
    close_total = sim.total_money()
    why = {}
    for t in sim.journal:
        if t.state == "REJECTED":
            key = ("Not enough balance" if t.note.startswith("Not enough") else
                   "Account does not exist" if t.note.startswith("No account") else
                   "Amount out of range" if "allowed range" in t.note else
                   "Same source and destination")
            why[key] = why.get(key, 0) + 1
    checks = {
        "money_balances": abs(close_total - (open_total + dep - wd)) < 1e-3,
        "min_balance": all(a.balance >= MIN_BAL[a.kind] - 1e-9 for a in sim.ledger),
        "fifo": [t.tid for t in sim.journal] == sorted(t.tid for t in sim.journal),
        "stack_sizes": all(len(a.activity) == sum(1 for t in done if a.number in (t.source, t.dest))
                           for a in sim.ledger[:300]),
    }
    t0 = time.perf_counter()
    while not sim.rollback.empty():
        sim.rollback_last()
    rb_ms = (time.perf_counter() - t0) * 1e3
    checks["rollback_restores"] = all(abs(a.balance - opening[a.number]) < 1e-6 for a in sim.ledger)
    checks["stacks_empty"] = all(a.activity.empty() for a in sim.ledger)
    R["bulk"] = {"accounts": 2000, "requests": 60000, "done": len(done), "rejected": 60000 - len(done),
                 "open_total": open_total, "deposits": dep, "withdrawals": wd, "close_total": close_total,
                 "expected": open_total + dep - wd, "rollback_ms": rb_ms, "why": why, "checks": checks,
                 "by_op": {op: [sum(1 for t in done if t.op == op),
                                sum(1 for t in sim.journal if t.op == op and t.state == "REJECTED")]
                           for op in ("deposit", "withdraw", "transfer")}}
    R["per_day"] = [[DAYS[d - 1], sum(t.amount for t in done if t.day == d and t.op == "deposit"),
                     sum(t.amount for t in done if t.day == d and t.op == "withdraw"),
                     sum(1 for t in done if t.day == d)] for d in range(1, 7)]
    print("bulk", R["bulk"], flush=True)

    # -------------------------------------------------------------- C. search cost
    res = []
    for n in (1_000, 10_000, 100_000, 1_000_000):
        b = BankSimulator()
        b.ledger = [Account(81001 + i, "", "Savings", 0.0) for i in range(n)]
        b.lookup = {a.number: a for a in b.ledger}
        rng = random.Random(n)
        hits = [rng.randint(81001, 81000 + n) for _ in range(1000)]
        misses = [81000 + n + rng.randint(1, n) for _ in range(1000)]
        k_lin = {1_000: 1000, 10_000: 500, 100_000: 200, 1_000_000: 60}[n]
        row = {"n": n,
               "lin_hit": float(np.mean([b.find_linear(x)[1] for x in hits[:k_lin]])),
               "lin_miss": float(np.mean([b.find_linear(x)[1] for x in misses[:max(10, k_lin // 4)]])),
               "bin_hit": float(np.mean([b.find_binary(x)[1] for x in hits])),
               "bin_miss": float(np.mean([b.find_binary(x)[1] for x in misses]))}
        gc.disable()
        t0 = time.perf_counter(); [b.find_linear(x) for x in hits[:k_lin]]
        row["lin_us"] = (time.perf_counter() - t0) / k_lin * 1e6
        t0 = time.perf_counter(); [b.find_binary(x) for x in hits]
        row["bin_us"] = (time.perf_counter() - t0) / 1000 * 1e6
        t0 = time.perf_counter()
        for _ in range(25):
            [b.find_hash(x) for x in hits]
        row["hash_us"] = (time.perf_counter() - t0) / 25000 * 1e6
        gc.enable()
        res.append(row)
        print("search", row, flush=True)
        del b
    R["search"] = res

    # -------------------------------------------------------------- D. throughput
    base = make_bank(20000, 21)
    snap = [(a.holder, a.kind, a.balance) for a in base.ledger]
    tp = []
    for m in (2_000, 10_000, 25_000, 50_000, 100_000, 150_000, 250_000):
        best = float("inf")
        for rep in range(7):
            b = BankSimulator()
            for h, k, bal in snap:
                b.create_account(h, k, bal)
            flood(b, m, 1000 * rep + m)
            gc.collect(); gc.disable()
            t0 = time.perf_counter(); b.serve_all(); best = min(best, time.perf_counter() - t0)
            gc.enable()
        tp.append({"m": m, "ms": best * 1e3, "us_each": best / m * 1e6})
    slope, icept = np.polyfit([r["m"] for r in tp], [r["ms"] for r in tp], 1)
    pred = np.polyval([slope, icept], [r["m"] for r in tp])
    mean_ms = np.mean([q["ms"] for q in tp])
    ss_res = sum((r["ms"] - p) ** 2 for r, p in zip(tp, pred))
    ss_tot = sum((r["ms"] - mean_ms) ** 2 for r in tp)
    R["throughput"] = tp
    R["fit"] = {"slope_us": slope * 1e3, "intercept_ms": icept, "r2": 1 - ss_res / ss_tot}
    print("tp", tp, R["fit"], flush=True)

    # linear vs binary lookup inside the queue server
    cmp_rows = []
    for n in (2_000, 10_000, 25_000, 50_000):
        row = {"n": n}
        for cls, key in ((BankSimulator, "binary_ms"), (LinearLookupBank, "linear_ms")):
            b = cls()
            for i in range(n):
                b.create_account("x", "Savings", 75000)
            flood(b, 2500, n)
            gc.collect(); gc.disable()
            t0 = time.perf_counter(); b.serve_all(); row[key] = (time.perf_counter() - t0) * 1e3
            gc.enable()
        cmp_rows.append(row)
    R["lookup_inside"] = cmp_rows
    print("lookup", cmp_rows, flush=True)

    # -------------------------------------------------------------- E. mini statement: stack vs journal scan
    ms_rows = []
    b = make_bank(800, 31)
    who = b.ledger[5].number
    for size in (2_000, 20_000, 200_000, 600_000):
        while len(b.journal) < size:
            flood(b, min(25_000, size - len(b.journal)), len(b.journal) + 7)
            b.serve_all()
        t0 = time.perf_counter()
        for _ in range(300):
            b.mini_statement(who, 5)
        s_us = (time.perf_counter() - t0) / 300 * 1e6
        t0 = time.perf_counter()
        for _ in range(4):
            [t for t in b.journal if t.state == "DONE" and who in (t.source, t.dest)][-5:]
        j_us = (time.perf_counter() - t0) / 4 * 1e6
        ms_rows.append({"journal": size, "stack_us": s_us, "scan_us": j_us})
    R["mini_stmt"] = ms_rows
    print("ministmt", ms_rows, flush=True)

    # -------------------------------------------------------------- F. counters
    day = {c: bank_day(c) for c in (2, 3, 4)}
    R["counters"] = {str(c): {k: v for k, v in d.items() if k != "length"} for c, d in day.items()}

    # ============================================================== CHARTS
    # 1. deposits vs withdrawals per working day
    pdf = pd.DataFrame([(d, "Deposits", x / 1e5) for d, x, _, _ in R["per_day"]] +
                       [(d, "Withdrawals", y / 1e5) for d, _, y, _ in R["per_day"]],
                       columns=["day", "flow", "lakh"])
    fig, ax = plt.subplots(figsize=(6.3, 3.3))
    sns.barplot(pdf, x="day", y="lakh", hue="flow", palette=[VIOLET, AMBER], width=0.72, gap=0.12,
                saturation=1, ax=ax)
    for c in ax.containers:
        ax.bar_label(c, fmt="%.0f", fontsize=7.5, padding=2, color=INK)
    ax.set(xlabel="Working day", ylabel="Value (Rs lakh)", title="Successful deposits and withdrawals by day")
    ax.legend(title=None, loc="upper left", bbox_to_anchor=(0, 1.02), ncol=2)
    ax.set_ylim(0, pdf.lakh.max() * 1.18)
    save(fig, "dw_by_day")

    # 2. per customer (horizontal)
    fdf = pd.DataFrame([(h.split()[0], "Credited", i / 1000) for h, i, o in flows] +
                       [(h.split()[0], "Debited", o / 1000) for h, i, o in flows], columns=["holder", "flow", "k"])
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    sns.barplot(fdf, y="holder", x="k", hue="flow", palette=[VIOLET, AMBER], orient="h", width=0.75, gap=0.1,
                saturation=1, ax=ax)
    ax.grid(axis="x", color="#ebeae6"); ax.grid(axis="y", visible=False)
    ax.set(xlabel="Amount (Rs thousand)", ylabel="", title="Credited vs debited per account (demo queue)")
    ax.legend(title=None, loc="lower right")
    save(fig, "dw_by_customer")

    # 3. rejection reasons
    wdf = pd.DataFrame(sorted(why.items(), key=lambda kv: -kv[1]), columns=["reason", "count"])
    wdf["reason"] = wdf["reason"].map(lambda r: textwrap.fill(r, 16))
    fig, ax = plt.subplots(figsize=(6.0, 2.9))
    sns.barplot(wdf, x="reason", y="count", color=VIOLET, width=0.55, saturation=1, ax=ax)
    ax.bar_label(ax.containers[0], labels=[f"{v:,}" for v in wdf["count"]], fontsize=8.5, padding=2)
    ax.set(xlabel="", ylabel="Requests", title=f"Rejected requests ({sum(why.values()):,} of 60,000)")
    ax.set_ylim(0, wdf["count"].max() * 1.15)
    ax.tick_params(axis="x", labelsize=8.5)
    save(fig, "rejections")

    # 4. search steps (grouped bars, log scale)
    sdf = pd.DataFrame([(f"{r['n']:,}", "Linear search", r["lin_hit"]) for r in res] +
                       [(f"{r['n']:,}", "Binary search", r["bin_hit"]) for r in res],
                       columns=["n", "method", "steps"])
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    sns.barplot(sdf, x="n", y="steps", hue="method", palette=[AMBER, VIOLET], width=0.7, gap=0.1,
                saturation=1, ax=ax)
    ax.set_yscale("log")
    for c in ax.containers:
        ax.bar_label(c, labels=[f"{v:,.0f}" if v >= 100 else f"{v:.1f}" for v in c.datavalues],
                     fontsize=7.5, padding=2)
    ax.set(xlabel="Number of accounts", ylabel="Average comparisons (log scale)",
           title="Comparisons needed to find an account")
    ax.legend(title=None, loc="upper left")
    save(fig, "search_steps")

    # 5. search time (log-log line)
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    ns = [r["n"] for r in res]
    for key, col, mk, lab in (("lin_us", AMBER, "D", "Linear search"), ("bin_us", VIOLET, "o", "Binary search"),
                              ("hash_us", AQUA, "s", "Hash table (dict)")):
        ax.plot(ns, [r[key] for r in res], marker=mk, color=col, lw=2, ms=6, label=lab)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.grid(axis="x", color="#ebeae6")
    ax.set(xlabel="Number of accounts (log scale)", ylabel="Microseconds per search (log scale)",
           title="Search time as the bank grows")
    ax.legend(loc="upper left")
    save(fig, "search_time")

    # 6. throughput with linear fit
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    ms_ = [r["m"] for r in tp]
    ax.scatter(ms_, [r["ms"] for r in tp], color=VIOLET, s=36, zorder=3, label="Measured")
    xx = np.linspace(0, max(ms_), 50)
    ax.plot(xx, np.polyval([slope, icept], xx), color=SOFT, lw=1.2, ls="--",
            label=f"Least-squares line (R² = {R['fit']['r2']:.4f})")
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, p: f"{v / 1000:.0f}k" if v else "0"))
    ax.set(xlabel="Requests waiting in the queue", ylabel="Time to serve all (ms)",
           title="Serving time vs queue length (20,000 accounts)")
    ax.legend(loc="upper left")
    save(fig, "throughput_fit")

    # 7. counters
    fig, ax = plt.subplots(figsize=(6.3, 3.3))
    for c, col in ((2, AMBER), (3, VIOLET), (4, AQUA)):
        ax.plot(range(len(day[c]["length"])), day[c]["length"], color=col, lw=1.6, label=f"{c} counters")
    ax.set(xlabel="Minutes since the bank opened", ylabel="Customers in the line",
           title="Length of the waiting line (2.2 arrivals per minute)")
    ax.legend(loc="upper left")
    save(fig, "counters")
    print(f"charts saved to {os.path.abspath(chart_dir)}")

    # -------------------------------------------------------------- summary
    with open(os.path.join(chart_dir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(R, fh, indent=1, default=str, ensure_ascii=False)

    print("\nBulk simulation checks:", R["bulk"]["checks"])
    for title, data in (("Search cost", R["search"]), ("Lookup inside the queue server", R["lookup_inside"]),
                        ("Throughput", R["throughput"]), ("Mini statement: stack vs journal scan", R["mini_stmt"])):
        print(f"\n{title}:")
        print(pd.DataFrame(data).round(3).to_string(index=False))
    print("fit:", R["fit"])
    print("\nCounters:")
    print(pd.DataFrame(R["counters"]).T.to_string())
    return R


# ======================================================================
def main():
    parser = argparse.ArgumentParser(description="Banking System Simulator (CIC-311 mini project)")
    parser.add_argument("--menu", action="store_true", help="open the interactive menu (Part E)")
    parser.add_argument("--experiments", action="store_true", help="run benchmarks and draw charts (Part F)")
    parser.add_argument("--all", action="store_true", help="run every part")
    args = parser.parse_args()

    bank = part_b()
    part_c(bank)
    part_d(bank)
    if args.menu or args.all:
        run_menu(bank)
    if args.experiments or args.all:
        run_experiments()


if __name__ == "__main__":
    main()
