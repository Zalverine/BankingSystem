"""
Banking System Simulator - desktop UI (Tkinter)

    python ui.py

Uses the BankSimulator from start.py: requests go into the LinkedQueue,
served transactions are pushed on the rollback HistoryStack, and every
account lookup is a binary search on the sorted ledger.
"""

import random
import tkinter as tk
from tkinter import ttk, messagebox

from start import (BankSimulator, TransactionError, DEMO_ACCOUNTS, DEMO_REQUESTS,
                   MIN_BAL, LIMIT_PER_TXN, rupees, FIRST, LAST, DAYS, flood)


def sample_bank(accounts=30, served=220, rolled_back=3, waiting=8, seed=7):
    """A believable bank for the UI: a week of served traffic (deposits, withdrawals,
    transfers and some invalid requests), a few rollbacks, and requests still queued."""
    rng = random.Random(seed)
    b = BankSimulator()
    for name in rng.sample([f"{f} {l}" for f in FIRST for l in LAST], accounts):
        kind = "Current" if rng.random() < 0.3 else "Savings"
        b.create_account(name, kind, round(rng.uniform(3_000, 95_000), -2))
    flood(b, served, seed + 1)            # days Mon..Sat, ~4 % junk requests
    b.serve_all()
    for _ in range(rolled_back):
        b.rollback_last()
    flood(b, waiting, seed + 2, days=1)   # still standing in the line
    for t in b.pending:
        t.day = 6
    return b

BG, PANEL, INK, SOFT = "#f6f5f2", "#ffffff", "#1d1d1b", "#6b6a66"
VIOLET, AMBER, AQUA, RED = "#6250d6", "#eda100", "#1baf7a", "#d0453a"


try:                                   # crisp text on scaled Windows displays
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except (AttributeError, OSError):
    pass


class BankUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Banking System Simulator")
        k = self.winfo_fpixels("1i") / 96          # 1.0 at 100 %, 1.5 at 150 % scaling
        w, h = min(int(1240 * k), self.winfo_screenwidth() - 40), min(int(760 * k), self.winfo_screenheight() - 80)
        self.geometry(f"{w}x{h}")
        self.minsize(int(980 * k), int(600 * k))
        self.k = k
        self.configure(bg=BG)
        self.bank = sample_bank()
        self._style()
        self._build()
        self.refresh()
        self.say(f"Loaded a sample bank: {len(self.bank.ledger)} accounts, {len(self.bank.journal)} served "
                 f"requests, {len(self.bank.pending)} still queued. See the Charts tab.")

    # ------------------------------------------------------------ styling
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=INK, font=("Segoe UI", 10))
        s.configure("Card.TLabelframe", background=PANEL, bordercolor="#dddbd5", relief="solid")
        s.configure("Card.TLabelframe.Label", background=PANEL, foreground=VIOLET, font=("Segoe UI", 10, "bold"))
        s.configure("Card.TFrame", background=PANEL)
        s.configure("Card.TLabel", background=PANEL)
        s.configure("Card.TRadiobutton", background=PANEL)
        s.configure("Stat.TLabel", background=PANEL, font=("Segoe UI", 15, "bold"), foreground=VIOLET)
        s.configure("StatCap.TLabel", background=PANEL, foreground=SOFT, font=("Segoe UI", 9))
        s.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        s.configure("Sub.TLabel", foreground=SOFT)
        s.configure("Accent.TButton", background=VIOLET, foreground="white", borderwidth=0, padding=(10, 5))
        s.map("Accent.TButton", background=[("active", "#4e3dc0"), ("disabled", "#b9b2ec")])
        s.configure("TButton", padding=(10, 5))
        s.configure("Treeview", rowheight=int(24 * self.k), fieldbackground=PANEL, background=PANEL)
        s.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#ebeae6")
        s.map("Treeview", background=[("selected", "#ddd8fb")], foreground=[("selected", INK)])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(14, 6))

    # ------------------------------------------------------------ layout
    def _build(self):
        head = ttk.Frame(self, padding=(16, 12, 16, 4))
        head.pack(fill="x")
        ttk.Label(head, text="🏦 Banking System Simulator", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="   queue = LinkedQueue (FIFO)  ·  history = HistoryStack (LIFO)  ·  lookup = binary search",
                  style="Sub.TLabel").pack(side="left", pady=(6, 0))

        # stats row
        stats = ttk.Frame(self, padding=(16, 4))
        stats.pack(fill="x")
        self.stat = {}
        for key, cap in (("accounts", "Accounts"), ("money", "Money in the bank"), ("queued", "Waiting in queue"),
                         ("rollback", "Rollback stack"), ("served", "Served (done / rejected)")):
            card = ttk.Frame(stats, style="Card.TFrame", padding=(14, 8))
            card.pack(side="left", padx=(0, 10), fill="x", expand=True)
            self.stat[key] = ttk.Label(card, text="0", style="Stat.TLabel")
            self.stat[key].pack(anchor="w")
            ttk.Label(card, text=cap, style="StatCap.TLabel").pack(anchor="w")

        body = ttk.Frame(self, padding=(16, 8, 16, 8))
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, width=300)
        left.pack(side="left", fill="y", padx=(0, 12))
        self._build_forms(left)

        self.tabs = ttk.Notebook(body)
        self.tabs.pack(side="left", fill="both", expand=True)
        self._build_accounts_tab()
        self._build_queue_tab()
        self._build_journal_tab()
        self._build_search_tab()
        self._build_charts_tab()

        self.status = tk.StringVar(value="Ready. Open an account or load the demo data.")
        bar = tk.Label(self, textvariable=self.status, anchor="w", bg="#ebeae6", fg=INK,
                       font=("Segoe UI", 9), padx=16, pady=4)
        bar.pack(fill="x", side="bottom")

    def _card(self, parent, title):
        f = ttk.Labelframe(parent, text=title, style="Card.TLabelframe", padding=10)
        f.pack(fill="x", pady=(0, 10))
        f.columnconfigure(1, weight=1)
        return f

    def _row(self, parent, r, label, widget):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=r, column=0, sticky="w", pady=3, padx=(0, 8))
        widget.grid(row=r, column=1, sticky="ew", pady=3)
        return widget

    def _build_forms(self, left):
        # open account
        f = self._card(left, "Open account")
        self.v_holder, self.v_kind, self.v_open = tk.StringVar(), tk.StringVar(value="Savings"), tk.StringVar()
        self._row(f, 0, "Holder", ttk.Entry(f, textvariable=self.v_holder))
        self._row(f, 1, "Type", ttk.Combobox(f, textvariable=self.v_kind, values=list(MIN_BAL), state="readonly"))
        self._row(f, 2, "Opening Rs", ttk.Entry(f, textvariable=self.v_open))
        ttk.Button(f, text="Open account", style="Accent.TButton", command=self.open_account) \
            .grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        # new request
        f = self._card(left, "New request  →  joins the queue")
        self.v_op, self.v_src, self.v_amt, self.v_dst = (tk.StringVar(value="deposit"), tk.StringVar(),
                                                         tk.StringVar(), tk.StringVar())
        ops = ttk.Frame(f, style="Card.TFrame")
        ops.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        for op in ("deposit", "withdraw", "transfer"):
            ttk.Radiobutton(ops, text=op.capitalize(), value=op, variable=self.v_op, style="Card.TRadiobutton",
                            command=self._toggle_dest).pack(side="left", padx=(0, 8))
        self._row(f, 1, "Account", ttk.Entry(f, textvariable=self.v_src))
        self._row(f, 2, "Amount Rs", ttk.Entry(f, textvariable=self.v_amt))
        self.e_dst = self._row(f, 3, "To account", ttk.Entry(f, textvariable=self.v_dst))
        ttk.Button(f, text="Add to queue", style="Accent.TButton", command=self.add_request) \
            .grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._toggle_dest()

        # actions
        f = self._card(left, "Teller")
        for r, (txt, cmd, sty) in enumerate((("Serve next  (dequeue)", self.serve_next, "Accent.TButton"),
                                             ("Serve whole queue", self.serve_all, "TButton"),
                                             ("Roll back last  (pop)", self.rollback, "TButton"),
                                             ("Load sample bank (30 accounts)", self.load_sample, "TButton"),
                                             ("Load demo data (8 accounts)", self.load_demo, "TButton"),
                                             ("Reset bank", self.reset, "TButton"))):
            ttk.Button(f, text=txt, style=sty, command=cmd).grid(row=r, column=0, columnspan=2, sticky="ew", pady=2)

    def _tree(self, parent, cols, widths, height=12):
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=height)
        for c, w in zip(cols, widths):
            tree.heading(c, text=c)
            tree.column(c, width=int(w * self.k), anchor="e" if c in ("Balance", "Amount", "Closing") else "w", stretch=True)
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        tree.tag_configure("DONE", foreground=AQUA)
        tree.tag_configure("REJECTED", foreground=RED)
        tree.tag_configure("ROLLED BACK", foreground=AMBER)
        tree.tag_configure("front", background="#f1eefe")
        return frame, tree

    def _build_accounts_tab(self):
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="Accounts")
        frame, self.t_acc = self._tree(tab, ("Number", "Holder", "Type", "Balance"), (90, 220, 90, 140))
        frame.pack(fill="both", expand=True)
        self.t_acc.bind("<<TreeviewSelect>>", self._on_account_select)
        self.stmt_title = ttk.Label(tab, text="Mini statement — select an account (top of its activity stack)",
                                    font=("Segoe UI", 10, "bold"))
        self.stmt_title.pack(anchor="w", pady=(10, 4))
        frame, self.t_stmt = self._tree(tab, ("Txn", "Operation", "Detail", "Amount"), (70, 110, 220, 120), height=5)
        frame.pack(fill="x")

    def _build_queue_tab(self):
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="Queue")
        ttk.Label(tab, text="Pending requests, front of the queue first. 'Serve next' takes the highlighted row.",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 6))
        frame, self.t_queue = self._tree(tab, ("Pos", "Txn", "Operation", "From", "To", "Amount"),
                                         (50, 70, 110, 100, 100, 120))
        frame.pack(fill="both", expand=True)

    def _build_journal_tab(self):
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="Journal")
        ttk.Label(tab, text="Every served request, newest first.", style="Sub.TLabel").pack(anchor="w", pady=(0, 6))
        frame, self.t_journal = self._tree(tab, ("Txn", "Operation", "From", "To", "Amount", "Result", "Note / closing"),
                                           (60, 90, 80, 80, 100, 110, 300))
        frame.pack(fill="both", expand=True)

    def _build_search_tab(self):
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="Search")
        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.v_find = tk.StringVar()
        ttk.Label(top, text="Account number").pack(side="left")
        e = ttk.Entry(top, textvariable=self.v_find, width=14)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda _: self.search_number())
        ttk.Button(top, text="Compare searches", style="Accent.TButton", command=self.search_number).pack(side="left")
        self.v_name = tk.StringVar()
        ttk.Label(top, text="     Name contains").pack(side="left")
        e = ttk.Entry(top, textvariable=self.v_name, width=14)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda _: self.search_name())
        ttk.Button(top, text="Find", command=self.search_name).pack(side="left")

        self.search_out = tk.Text(tab, height=6, wrap="word", font=("Consolas", 10), bg=PANEL, relief="flat",
                                  padx=8, pady=6)
        self.search_out.pack(fill="x", pady=10)
        ttk.Label(tab, text="Binary search trace", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        frame, self.t_trace = self._tree(tab, ("Step", "LOW", "HIGH", "MID", "L[MID].number"),
                                         (60, 80, 80, 80, 140), height=8)
        frame.pack(fill="both", expand=True, pady=(4, 0))

    # ------------------------------------------------------------ helpers
    def _toggle_dest(self):
        self.e_dst.configure(state="normal" if self.v_op.get() == "transfer" else "disabled")

    def say(self, msg, error=False):
        self.status.set(("⚠  " if error else "✓  ") + msg)

    @staticmethod
    def _num(text, what, cast=float):
        try:
            return cast(text.strip().replace(",", ""))
        except ValueError:
            raise TransactionError(f"{what} must be a number") from None

    # ------------------------------------------------------------ actions
    def open_account(self):
        try:
            holder = self.v_holder.get().strip()
            if not holder:
                raise TransactionError("Enter the holder's name")
            n = self.bank.create_account(holder, self.v_kind.get(), self._num(self.v_open.get(), "Opening balance"))
        except TransactionError as e:
            return self.say(str(e), error=True)
        self.v_holder.set(""); self.v_open.set("")
        self.v_src.set(str(n))
        self.refresh()
        self.say(f"Opened account {n} for {holder}")

    def add_request(self):
        try:
            op = self.v_op.get()
            src = self._num(self.v_src.get(), "Account", int)
            amt = self._num(self.v_amt.get(), "Amount")
            dst = self._num(self.v_dst.get(), "To account", int) if op == "transfer" else None
        except TransactionError as e:
            return self.say(str(e), error=True)
        t = self.bank.request(op, src, amt, dst)
        self.v_amt.set("")
        self.refresh()
        self.say(f"Queued {t.describe()}  —  {len(self.bank.pending)} waiting "
                 f"(checks happen when it is served; limit Rs {LIMIT_PER_TXN:,} per txn)")

    def serve_next(self):
        if self.bank.pending.empty():
            return self.say("The queue is empty", error=True)
        t = self.bank.serve_next()
        self.refresh()
        if t.state == "DONE":
            self.say(f"Served {t.describe()}  →  balance {rupees(t.closing)}")
        else:
            self.say(f"Rejected {t.describe()}: {t.note}", error=True)

    def serve_all(self):
        if self.bank.pending.empty():
            return self.say("The queue is empty", error=True)
        served = self.bank.serve_all()
        ok = sum(t.state == "DONE" for t in served)
        self.refresh()
        self.tabs.select(2)
        self.say(f"Served {len(served)} requests: {ok} done, {len(served) - ok} rejected")

    def rollback(self):
        try:
            t = self.bank.rollback_last()
        except TransactionError as e:
            return self.say(str(e), error=True)
        self.refresh()
        self.say(f"Rolled back {t.describe()}  —  {len(self.bank.rollback)} left on the stack")

    def load_sample(self):
        if self.bank.ledger and not messagebox.askyesno("Load sample", "Replace the current bank with sample data?"):
            return
        self.bank = sample_bank(seed=random.randint(1, 10_000))
        self.refresh()
        self.tabs.select(4)
        self.say(f"Loaded a sample bank: {len(self.bank.ledger)} accounts, {len(self.bank.journal)} served "
                 f"requests, {len(self.bank.pending)} still queued")

    def load_demo(self):
        if self.bank.ledger and not messagebox.askyesno("Load demo", "Replace the current bank with the demo data?"):
            return
        self.bank = BankSimulator()
        for holder, kind, opening in DEMO_ACCOUNTS:
            self.bank.create_account(holder, kind, opening)
        for op, s, amt, d in DEMO_REQUESTS:
            self.bank.request(op, s, amt, d)
        self.refresh()
        self.tabs.select(1)
        self.say("Loaded 8 accounts and 12 queued requests — press 'Serve next' to step through them")

    def reset(self):
        if self.bank.ledger and not messagebox.askyesno("Reset", "Delete every account and transaction?"):
            return
        self.bank = BankSimulator()
        self.refresh()
        self.say("Bank reset")

    def search_number(self):
        out = self.search_out
        out.delete("1.0", "end")
        for i in self.t_trace.get_children():
            self.t_trace.delete(i)
        try:
            n = self._num(self.v_find.get(), "Account number", int)
        except TransactionError as e:
            return self.say(str(e), error=True)
        trace = []
        acc, b_steps = self.bank.find_binary(n, log=trace)
        _, l_steps = self.bank.find_linear(n)
        for row in trace:
            self.t_trace.insert("", "end", values=row)
        out.insert("end", (f"{acc.number}  {acc.holder}  ({acc.kind})  balance {rupees(acc.balance)}\n\n"
                           if acc else f"No account numbered {n}\n\n"))
        out.insert("end", f"binary search : {b_steps:>6} comparisons\n"
                          f"linear search : {l_steps:>6} comparisons\n"
                          f"hash lookup   : {1:>6} probe (dict)\n")
        self.say(f"Searched {len(self.bank.ledger)} accounts for {n}")

    def search_name(self):
        part = self.v_name.get().strip()
        out = self.search_out
        out.delete("1.0", "end")
        hits = self.bank.find_by_name(part) if part else []
        out.insert("end", f"{len(hits)} account(s) with '{part}' in the name:\n")
        for a in hits:
            out.insert("end", f"  {a.number}  {a.holder:<20} {a.kind:<8} {rupees(a.balance)}\n")

    def _on_account_select(self, _=None):
        sel = self.t_acc.selection()
        for i in self.t_stmt.get_children():
            self.t_stmt.delete(i)
        if not sel:
            return
        number = int(sel[0])
        self.v_src.set(str(number))
        self.stmt_title.configure(text=f"Mini statement of {number} — newest first (top of its activity stack)")
        for t in self.bank.mini_statement(number, 5):
            if t.op == "transfer":
                detail = f"to {t.dest}" if t.source == number else f"from {t.source}"
            else:
                detail = "—"
            sign = "+" if t.op == "deposit" or (t.op == "transfer" and t.dest == number) else "−"
            self.t_stmt.insert("", "end", values=(f"#{t.tid}", t.op.capitalize(), detail,
                                                  f"{sign} {t.amount:,.2f}"))

    # ------------------------------------------------------------ refresh
    def refresh(self):
        b = self.bank
        done = sum(t.state != "REJECTED" for t in b.journal)
        self.stat["accounts"].configure(text=f"{len(b.ledger):,}")
        self.stat["money"].configure(text=rupees(b.total_money()))
        self.stat["queued"].configure(text=f"{len(b.pending):,}")
        self.stat["rollback"].configure(text=f"{len(b.rollback):,}")
        self.stat["served"].configure(text=f"{done} / {len(b.journal) - done}")

        selected = self.t_acc.selection()
        for tree in (self.t_acc, self.t_queue, self.t_journal):
            tree.delete(*tree.get_children())
        for a in b.ledger:
            self.t_acc.insert("", "end", iid=str(a.number),
                              values=(a.number, a.holder, a.kind, f"{a.balance:,.2f}"))
        if selected and self.t_acc.exists(selected[0]):
            self.t_acc.selection_set(selected[0])
            self._on_account_select()
        for pos, t in enumerate(b.pending, 1):
            self.t_queue.insert("", "end", tags=("front",) if pos == 1 else (),
                                values=(pos, f"#{t.tid}", t.op.capitalize(), t.source, t.dest or "—",
                                        f"{t.amount:,.2f}"))
        for t in reversed(b.journal):
            note = rupees(t.closing) if t.state == "DONE" else t.note
            self.t_journal.insert("", "end", tags=(t.state,),
                                  values=(f"#{t.tid}", t.op.capitalize(), t.source, t.dest or "—",
                                          f"{t.amount:,.2f}", t.state, note))
        self.tabs.tab(1, text=f"Queue ({len(b.pending)})")
        self.tabs.tab(2, text=f"Journal ({len(b.journal)})")
        self.draw_charts()

    # ------------------------------------------------------------ charts
    def _build_charts_tab(self):
        tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(tab, text="Charts")
        self.chart_tab, self.fig = tab, None
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except ImportError:
            ttk.Label(tab, text="Install matplotlib to see charts:  pip install matplotlib").pack(pady=40)
            return
        self.fig = Figure(figsize=(8, 5), dpi=78 * self.k, facecolor=BG)
        self.canvas = FigureCanvasTkAgg(self.fig, master=tab)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.tabs.bind("<<NotebookTabChanged>>", lambda _: self.draw_charts())

    def draw_charts(self):
        if self.fig is None or self.tabs.select() != str(self.chart_tab):
            return                      # only redraw while the tab is visible
        b, fig = self.bank, self.fig
        fig.clear()
        if not b.ledger:
            fig.text(0.5, 0.5, "No accounts yet", ha="center", color=SOFT, fontsize=12)
            self.canvas.draw_idle()
            return
        done = [t for t in b.journal if t.state == "DONE"]
        (a1, a2), (a3, a4) = fig.subplots(2, 2)

        def tidy(ax, title):
            ax.set_title(title, fontsize=9.5, fontweight="bold", color=INK, loc="left")
            ax.set_facecolor(PANEL)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                ax.spines[side].set_color("#c9c7c0")
            ax.tick_params(colors=SOFT, labelsize=7.5)

        # 1. top balances
        top = sorted(b.ledger, key=lambda a: a.balance)[-10:]
        a1.barh([a.holder for a in top], [a.balance / 1000 for a in top],
                color=[VIOLET if a.kind == "Savings" else AQUA for a in top], height=0.65)
        a1.set_xlabel("Rs thousand  (violet = Savings, green = Current)", fontsize=7.5, color=SOFT)
        tidy(a1, "Top 10 balances")

        # 2. deposits vs withdrawals per day
        days = sorted({t.day for t in done}) or [1]
        dep = [sum(t.amount for t in done if t.day == d and t.op == "deposit") / 1000 for d in days]
        wd = [sum(t.amount for t in done if t.day == d and t.op == "withdraw") / 1000 for d in days]
        x = range(len(days))
        a2.bar([i - 0.2 for i in x], dep, width=0.4, color=VIOLET, label="Deposits")
        a2.bar([i + 0.2 for i in x], wd, width=0.4, color=AMBER, label="Withdrawals")
        a2.set_xticks(list(x), [DAYS[d - 1] if 1 <= d <= len(DAYS) else str(d) for d in days])
        a2.set_ylabel("Rs thousand", fontsize=7.5, color=SOFT)
        a2.legend(frameon=False, fontsize=7.5)
        tidy(a2, "Deposits vs withdrawals by day")

        # 3. requests by operation and outcome (stacked)
        ops = ("deposit", "withdraw", "transfer")
        stack = [(st, col) for st, col in (("DONE", AQUA), ("ROLLED BACK", AMBER), ("REJECTED", RED))]
        bottom = [0] * 3
        for st, col in stack:
            vals = [sum(1 for t in b.journal if t.op == op and t.state == st) for op in ops]
            a3.bar([o.capitalize() for o in ops], vals, bottom=bottom, color=col, width=0.55,
                   label=st.capitalize())
            bottom = [p + v for p, v in zip(bottom, vals)]
        a3.legend(frameon=False, fontsize=7.5, loc="upper right")
        a3.set_ylabel("Requests", fontsize=7.5, color=SOFT)
        tidy(a3, f"Served requests by outcome ({len(b.journal)})")

        # 4. rejection reasons
        why = {}
        for t in b.journal:
            if t.state == "REJECTED":
                key = ("Not enough balance" if t.note.startswith("Not enough") else
                       "No such account" if t.note.startswith("No account") else
                       "Amount out of range" if "allowed range" in t.note else "Same account")
                why[key] = why.get(key, 0) + 1
        if why:
            items = sorted(why.items(), key=lambda kv: kv[1])
            a4.barh([k for k, _ in items], [v for _, v in items], color=RED, height=0.55)
            for i, (_, v) in enumerate(items):
                a4.text(v, i, f" {v}", va="center", fontsize=7.5, color=INK)
        else:
            a4.text(0.5, 0.5, "No rejections", ha="center", va="center", color=SOFT, transform=a4.transAxes)
            a4.set_xticks([]); a4.set_yticks([])
        tidy(a4, "Why requests were rejected")

        fig.tight_layout(pad=1.2, h_pad=1.6, w_pad=2)
        self.canvas.draw_idle()


if __name__ == "__main__":
    BankUI().mainloop()
