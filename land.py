import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from collections import OrderedDict
import math

# ─── SIMULATOR CORE ──────────────────────────────────────────────────────────

class TLBSimulator:
    def __init__(self, page_size, num_pages, tlb_size, policy, tlb_time, mem_time):
        self.page_size  = page_size
        self.num_pages  = num_pages
        self.tlb_size   = tlb_size
        self.policy     = policy
        self.tlb_time   = tlb_time
        self.mem_time   = mem_time

        self.page_table = {}      # page -> frame
        self.tlb        = OrderedDict()   # page -> frame (ordered for FIFO/LRU)
        self.next_frame = 0
        self.results    = []

    def _tlb_lookup(self, page):
        return self.tlb.get(page, None)

    def _tlb_insert(self, page, frame):
        replaced = None
        if len(self.tlb) >= self.tlb_size:
            if self.policy == "FIFO":
                evict_page = next(iter(self.tlb))
            else:  # LRU
                evict_page = next(iter(self.tlb))
            replaced = evict_page
            del self.tlb[evict_page]
        self.tlb[page] = frame
        return replaced

    def _update_lru(self, page):
        frame = self.tlb[page]
        del self.tlb[page]
        self.tlb[page] = frame

    def _alloc_frame(self, page):
        if page not in self.page_table:
            self.page_table[page] = self.next_frame
            self.next_frame += 1
        return self.page_table[page]

    def access(self, virtual_addr):
        page   = virtual_addr // self.page_size
        offset = virtual_addr  % self.page_size

        tlb_before = dict(self.tlb)
        entry = self._tlb_lookup(page)
        hit = entry is not None
        replaced = None

        if hit:
            frame = entry
            if self.policy == "LRU":
                self._update_lru(page)
        else:
            frame = self._alloc_frame(page)
            replaced = self._tlb_insert(page, frame)

        phys_addr  = frame * self.page_size + offset
        tlb_after  = dict(self.tlb)
        pt_snap    = dict(self.page_table)

        result = {
            "virtual_addr": virtual_addr,
            "page": page,
            "offset": offset,
            "hit": hit,
            "frame": frame,
            "phys_addr": phys_addr,
            "replaced": replaced,
            "tlb_before": tlb_before,
            "tlb_after": tlb_after,
            "page_table": pt_snap,
        }
        self.results.append(result)
        return result

    def summary(self):
        n     = len(self.results)
        hits  = sum(1 for r in self.results if r["hit"])
        misses = n - hits
        hit_ratio = hits / n if n else 0
        miss_ratio = 1 - hit_ratio
        eat = hit_ratio * (self.tlb_time + self.mem_time) + \
              miss_ratio * (self.tlb_time + 2 * self.mem_time)
        return {
            "total": n, "hits": hits, "misses": misses,
            "hit_ratio": hit_ratio, "miss_ratio": miss_ratio,
            "eat": eat
        }

# ─── GUI ─────────────────────────────────────────────────────────────────────

BG      = "#050a0f"
PANEL   = "#0b1520"
BORDER  = "#0d2a3a"
ACCENT  = "#00d4ff"
GREEN   = "#00ff88"
RED     = "#ff3366"
YELLOW  = "#ffcc00"
TEXT    = "#c8e6f0"
DIM     = "#4a7a8a"

def make_style():
    s = ttk.Style()
    s.theme_use("clam")

    s.configure(".", background=BG, foreground=TEXT, font=("Courier New", 10))
    s.configure("TFrame", background=BG)
    s.configure("TLabel", background=BG, foreground=DIM, font=("Courier New", 9))
    s.configure("TLabelframe", background=PANEL, foreground=ACCENT,
                font=("Courier New", 9, "bold"), bordercolor=BORDER, relief="flat")
    s.configure("TLabelframe.Label", background=PANEL, foreground=ACCENT,
                font=("Courier New", 9, "bold"))
    s.configure("TEntry", fieldbackground="#0a0f18", foreground=ACCENT,
                font=("Courier New", 10), insertcolor=ACCENT)
    s.configure("TCombobox", fieldbackground="#0a0f18", foreground=ACCENT,
                font=("Courier New", 10))
    s.configure("TButton", background="#0d2a3a", foreground=ACCENT,
                font=("Courier New", 9, "bold"), borderwidth=1, focusthickness=0)
    s.map("TButton", background=[("active", "#1a3d50")])

    s.configure("Hit.TButton",  background="#002a18", foreground=GREEN)
    s.configure("Miss.TButton", background="#2a0010", foreground=RED)

    # Treeview
    s.configure("Treeview",
                background="#0b1520", foreground=TEXT,
                fieldbackground="#0b1520", font=("Courier New", 9),
                rowheight=22, bordercolor=BORDER)
    s.configure("Treeview.Heading",
                background="#071018", foreground=ACCENT,
                font=("Courier New", 9, "bold"), relief="flat")
    s.map("Treeview", background=[("selected", "#1a3d50")])
    return s

class TLBApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TLB SIMULATOR")
        self.configure(bg=BG)
        self.geometry("1380x820")
        self.resizable(True, True)
        make_style()

        self.sim = None
        self.steps = []
        self.step_idx = 0
        self.step_mode = False

        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Title
        title_frame = tk.Frame(self, bg=BG, pady=10)
        title_frame.pack(fill=tk.X)
        tk.Label(title_frame, text="TLB SIMULATOR",
                 bg=BG, fg=ACCENT, font=("Courier New", 18, "bold")).pack()
        tk.Label(title_frame, text="TRANSLATION LOOKASIDE BUFFER — MEMORY MANAGEMENT UNIT",
                 bg=BG, fg=DIM, font=("Courier New", 8)).pack()

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill=tk.X)

        # Main layout
        main = tk.Frame(self, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel
        left = tk.Frame(main, bg=BG, width=340)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left.pack_propagate(False)
        self._build_left(left)

        # Right panel
        right = tk.Frame(main, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_right(right)

    def _lf(self, parent, text, **kw):
        f = ttk.LabelFrame(parent, text=f"  {text}  ", padding=(8, 6), **kw)
        return f

    def _label_entry(self, parent, label_text, default, row):
        tk.Label(parent, text=label_text, bg=PANEL, fg=DIM,
                 font=("Courier New", 8)).grid(row=row, column=0, sticky="w", padx=6, pady=2)
        var = tk.StringVar(value=str(default))
        e = tk.Entry(parent, textvariable=var, bg="#0a0f18", fg=ACCENT,
                     font=("Courier New", 10), insertbackground=ACCENT,
                     relief="flat", bd=1, highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=ACCENT, width=14)
        e.grid(row=row, column=1, sticky="ew", padx=6, pady=2)
        return var

    def _build_left(self, parent):
        cf = self._lf(parent, "⬡ CONFIGURATION")
        cf.pack(fill=tk.X, pady=(0, 8))
        cf.configure(style="TLabelframe")

        # Addresses text area
        tk.Label(cf, text="Virtual Addresses (space/comma separated):",
                 bg=PANEL, fg=DIM, font=("Courier New", 8)).grid(
                 row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(4,2))
        self.addr_text = tk.Text(cf, height=4, bg="#0a0f18", fg=ACCENT,
                                  font=("Courier New", 10), insertbackground=ACCENT,
                                  relief="flat", bd=1, highlightthickness=1,
                                  highlightbackground=BORDER, highlightcolor=ACCENT)
        self.addr_text.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=2)
        self.addr_text.insert("1.0", "0 512 1024 1536 2048 512 1024 3072 4096 512")
        cf.columnconfigure(1, weight=1)

        self.page_size_var = self._label_entry(cf, "Page Size (bytes):", 256, 2)
        self.num_pages_var = self._label_entry(cf, "Number of Pages:",   8,   3)
        self.tlb_size_var  = self._label_entry(cf, "TLB Size (entries):", 4,  4)

        tk.Label(cf, text="Replacement Policy:", bg=PANEL, fg=DIM,
                 font=("Courier New", 8)).grid(row=5, column=0, sticky="w", padx=6, pady=2)
        self.policy_var = tk.StringVar(value="FIFO")
        combo = ttk.Combobox(cf, textvariable=self.policy_var,
                             values=["FIFO", "LRU"], state="readonly", width=12)
        combo.grid(row=5, column=1, sticky="ew", padx=6, pady=2)

        self.tlb_time_var = self._label_entry(cf, "TLB Hit Time (ns):",     10,  6)
        self.mem_time_var = self._label_entry(cf, "Memory Access Time (ns):", 100, 7)

        # Buttons
        bf = tk.Frame(parent, bg=BG)
        bf.pack(fill=tk.X, pady=4)
        btn_run   = tk.Button(bf, text="▶  RUN ALL", command=self.run_full,
                              bg=ACCENT, fg="#000", font=("Courier New", 9, "bold"),
                              relief="flat", cursor="hand2", padx=10)
        btn_step  = tk.Button(bf, text="⧖  STEP MODE", command=self.start_step,
                              bg="#0d2a3a", fg=YELLOW, font=("Courier New", 9, "bold"),
                              relief="flat", cursor="hand2")
        btn_reset = tk.Button(bf, text="↺  RESET", command=self.reset_all,
                              bg="#0d2a3a", fg=DIM, font=("Courier New", 9, "bold"),
                              relief="flat", cursor="hand2")
        btn_run.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        btn_step.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        btn_reset.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # Step controls
        self.step_frame = tk.Frame(parent, bg=BG)
        self.step_frame.pack(fill=tk.X, pady=2)
        self.btn_prev = tk.Button(self.step_frame, text="◀ PREV", command=self.step_prev,
                                  bg="#0d2a3a", fg=ACCENT, font=("Courier New", 8, "bold"),
                                  relief="flat", cursor="hand2")
        self.btn_next = tk.Button(self.step_frame, text="NEXT ▶", command=self.step_next,
                                  bg="#0d2a3a", fg=ACCENT, font=("Courier New", 8, "bold"),
                                  relief="flat", cursor="hand2")
        self.step_lbl = tk.Label(self.step_frame, text="", bg=BG, fg=DIM,
                                  font=("Courier New", 8))
        self.btn_prev.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        self.btn_next.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.step_lbl.pack(fill=tk.X, pady=2)

        # Log
        lf = self._lf(parent, "⬡ EVENT LOG")
        lf.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log_text = tk.Text(lf, bg="#0a0f18", fg=DIM, font=("Courier New", 8),
                                 relief="flat", height=10, state=tk.DISABLED,
                                 insertbackground=ACCENT)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_config("hit",     foreground=GREEN)
        self.log_text.tag_config("miss",    foreground=RED)
        self.log_text.tag_config("replace", foreground=YELLOW)
        self.log_text.tag_config("info",    foreground=ACCENT)

    def _build_right(self, parent):
        # Top: results table
        rf = self._lf(parent, "⬡ ADDRESS TRANSLATION RESULTS")
        rf.pack(fill=tk.X, pady=(0, 8))

        cols = ("#", "Virtual Addr", "Page No.", "Offset",
                "TLB Result", "Frame No.", "Physical Addr", "Replaced")
        self.result_tree = ttk.Treeview(rf, columns=cols, show="headings",
                                         height=7, selectmode="browse")
        widths = [35, 100, 80, 80, 100, 90, 110, 80]
        for c, w in zip(cols, widths):
            self.result_tree.heading(c, text=c)
            self.result_tree.column(c, width=w, anchor="center")
        self.result_tree.tag_configure("hit",    background="#00200e", foreground=GREEN)
        self.result_tree.tag_configure("miss",   background="#200008", foreground=RED)
        self.result_tree.tag_configure("active", background="#001a26", foreground=ACCENT)

        sb = ttk.Scrollbar(rf, orient=tk.VERTICAL, command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=sb.set)
        self.result_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sb.pack(side=tk.LEFT, fill=tk.Y)

        # Middle: TLB + Page Table
        mid = tk.Frame(parent, bg=BG)
        mid.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # TLB state
        tlb_f = self._lf(mid, "⬡ TLB STATE")
        tlb_f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        tlb_cols = ("Slot", "Page", "Frame", "Status")
        self.tlb_tree = ttk.Treeview(tlb_f, columns=tlb_cols, show="headings",
                                      height=6, selectmode="none")
        for c, w in zip(tlb_cols, [50, 70, 70, 120]):
            self.tlb_tree.heading(c, text=c)
            self.tlb_tree.column(c, width=w, anchor="center")
        self.tlb_tree.tag_configure("hit_slot",   background="#001a26", foreground=ACCENT)
        self.tlb_tree.tag_configure("new_entry",  background="#00200e", foreground=GREEN)
        self.tlb_tree.tag_configure("replaced",   background="#1a1000", foreground=YELLOW)
        self.tlb_tree.tag_configure("empty",      foreground=DIM)
        self.tlb_tree.pack(fill=tk.BOTH, expand=True)

        # Page table
        pt_f = self._lf(mid, "⬡ PAGE TABLE")
        pt_f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        pt_cols = ("Page", "Frame", "Status")
        self.pt_tree = ttk.Treeview(pt_f, columns=pt_cols, show="headings",
                                     height=6, selectmode="none")
        for c, w in zip(pt_cols, [60, 70, 100]):
            self.pt_tree.heading(c, text=c)
            self.pt_tree.column(c, width=w, anchor="center")
        self.pt_tree.tag_configure("loaded",  foreground=GREEN)
        self.pt_tree.tag_configure("empty",   foreground=DIM)
        self.pt_tree.pack(fill=tk.BOTH, expand=True)

        # Summary
        sf = self._lf(parent, "⬡ SUMMARY STATISTICS")
        sf.pack(fill=tk.X)

        stats_row = tk.Frame(sf, bg=PANEL)
        stats_row.pack(fill=tk.X, pady=(0, 8))

        labels = ["TOTAL", "HITS", "MISSES", "HIT RATIO", "MISS RATIO"]
        colors = [ACCENT, GREEN, RED, ACCENT, RED]
        self.stat_vars = []
        for i, (lbl, col) in enumerate(zip(labels, colors)):
            box = tk.Frame(stats_row, bg="#0a0f18", relief="flat",
                           highlightthickness=1, highlightbackground=BORDER)
            box.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
            v = tk.StringVar(value="—")
            tk.Label(box, textvariable=v, bg="#0a0f18", fg=col,
                     font=("Courier New", 18, "bold")).pack(pady=(8, 2))
            tk.Label(box, text=lbl, bg="#0a0f18", fg=DIM,
                     font=("Courier New", 7)).pack(pady=(0, 8))
            self.stat_vars.append(v)

        eat_row = tk.Frame(sf, bg=PANEL)
        eat_row.pack(fill=tk.X, pady=(0, 4))
        self.eat_var = tk.StringVar(value="—")
        self.eat_formula_var = tk.StringVar(value="—")
        eat_box = tk.Frame(eat_row, bg="#0a0f18", highlightthickness=1,
                           highlightbackground=BORDER)
        eat_box.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
        tk.Label(eat_box, textvariable=self.eat_var, bg="#0a0f18", fg=GREEN,
                 font=("Courier New", 14, "bold")).pack(side=tk.LEFT, padx=12, pady=8)
        tk.Label(eat_box, text="ns EAT", bg="#0a0f18", fg=DIM,
                 font=("Courier New", 8)).pack(side=tk.LEFT)
        f2 = tk.Frame(eat_row, bg="#0a0f18", highlightthickness=1,
                      highlightbackground=BORDER)
        f2.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
        tk.Label(f2, textvariable=self.eat_formula_var, bg="#0a0f18", fg=DIM,
                 font=("Courier New", 8)).pack(padx=12, pady=8)

    # ── Simulation Control ────────────────────────────────────────────────────

    def _parse_input(self):
        raw   = self.addr_text.get("1.0", tk.END)
        parts = raw.replace(",", " ").split()
        addrs = []
        for p in parts:
            try: addrs.append(int(p))
            except: pass
        if not addrs:
            messagebox.showerror("Input Error", "No valid virtual addresses found.")
            return None
        try:
            ps = int(self.page_size_var.get())
            np_ = int(self.num_pages_var.get())
            ts = int(self.tlb_size_var.get())
            tt = int(self.tlb_time_var.get())
            mt = int(self.mem_time_var.get())
        except ValueError:
            messagebox.showerror("Input Error", "Invalid numeric parameter.")
            return None
        pol = self.policy_var.get()
        self.sim = TLBSimulator(ps, np_, ts, pol, tt, mt)
        return addrs

    def run_full(self):
        addrs = self._parse_input()
        if addrs is None: return
        self.steps = [self.sim.access(a) for a in addrs]
        self.step_mode = False
        self._render_all()

    def start_step(self):
        addrs = self._parse_input()
        if addrs is None: return
        self.steps = [self.sim.access(a) for a in addrs]
        self.step_mode = True
        self.step_idx = 0
        self._clear_results()
        self._render_step(0)

    def step_next(self):
        if not self.step_mode or not self.steps: return
        if self.step_idx < len(self.steps) - 1:
            self.step_idx += 1
        self._render_step(self.step_idx)

    def step_prev(self):
        if not self.step_mode or not self.steps: return
        if self.step_idx > 0:
            self.step_idx -= 1
        self._render_step(self.step_idx)

    def reset_all(self):
        self.sim = None
        self.steps = []
        self.step_idx = 0
        self.step_mode = False
        self._clear_results()
        self.step_lbl.config(text="")

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _clear_results(self):
        for t in [self.result_tree, self.tlb_tree, self.pt_tree]:
            t.delete(*t.get_children())
        for v in self.stat_vars: v.set("—")
        self.eat_var.set("—")
        self.eat_formula_var.set("—")
        self._clear_log()

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _render_all(self):
        self._clear_results()
        for i, s in enumerate(self.steps):
            tag = "hit" if s["hit"] else "miss"
            rep = f"PG {s['replaced']}" if s["replaced"] is not None else "—"
            self.result_tree.insert("", tk.END, tags=(tag,), values=(
                i+1, s["virtual_addr"], s["page"], s["offset"],
                "HIT ✓" if s["hit"] else "MISS ✗",
                s["frame"], s["phys_addr"], rep
            ))
            self._log(s, i)
        last = self.steps[-1]
        self._render_tlb(last["tlb_after"], last, self.sim.tlb_size)
        self._render_pt(last["page_table"], self.sim.num_pages)
        self._render_summary()

    def _render_step(self, idx):
        self.result_tree.delete(*self.result_tree.get_children())
        for i, s in enumerate(self.steps[:idx+1]):
            tag = "active" if i == idx else ("hit" if s["hit"] else "miss")
            rep = f"PG {s['replaced']}" if s["replaced"] is not None else "—"
            iid = self.result_tree.insert("", tk.END, tags=(tag,), values=(
                i+1, s["virtual_addr"], s["page"], s["offset"],
                "HIT ✓" if s["hit"] else "MISS ✗",
                s["frame"], s["phys_addr"], rep
            ))
            if i == idx:
                self.result_tree.see(iid)

        cur = self.steps[idx]
        self._render_tlb(cur["tlb_after"], cur, self.sim.tlb_size)
        self._render_pt(cur["page_table"], self.sim.num_pages)
        self._log(cur, idx)
        self._render_summary(self.steps[:idx+1])
        self.step_lbl.config(text=f"Step {idx+1} / {len(self.steps)}")

    def _render_tlb(self, tlb_after, cur, tlb_size):
        self.tlb_tree.delete(*self.tlb_tree.get_children())
        entries = list(tlb_after.items())
        for i in range(tlb_size):
            if i < len(entries):
                pg, fr = entries[i]
                if not cur["hit"] and pg == cur["page"]:
                    tag = "replaced" if cur["replaced"] is not None else "new_entry"
                elif cur["hit"] and pg == cur["page"]:
                    tag = "hit_slot"
                else:
                    tag = ""
                self.tlb_tree.insert("", tk.END, tags=(tag,), values=(
                    i, f"PG {pg}", f"FR {fr}", "● In TLB"
                ))
            else:
                self.tlb_tree.insert("", tk.END, tags=("empty",), values=(
                    i, "—", "—", "○ Empty"
                ))

    def _render_pt(self, pt, num_pages):
        self.pt_tree.delete(*self.pt_tree.get_children())
        for pg in range(num_pages):
            if pg in pt:
                self.pt_tree.insert("", tk.END, tags=("loaded",), values=(
                    pg, pt[pg], "● Loaded"
                ))
            else:
                self.pt_tree.insert("", tk.END, tags=("empty",), values=(
                    pg, "—", "○ Not Loaded"
                ))

    def _render_summary(self, steps=None):
        s_list = steps if steps is not None else self.steps
        n = len(s_list)
        hits   = sum(1 for s in s_list if s["hit"])
        misses = n - hits
        hr     = hits / n if n else 0
        mr     = 1 - hr
        tt     = self.sim.tlb_time
        mt     = self.sim.mem_time
        eat    = hr * (tt + mt) + mr * (tt + 2 * mt)

        self.stat_vars[0].set(str(n))
        self.stat_vars[1].set(str(hits))
        self.stat_vars[2].set(str(misses))
        self.stat_vars[3].set(f"{hr*100:.1f}%")
        self.stat_vars[4].set(f"{mr*100:.1f}%")
        self.eat_var.set(f"{eat:.2f}")
        self.eat_formula_var.set(
            f"EAT = h×(T+M) + (1-h)×(T+2M) | h={hr*100:.0f}%"
        )

    def _log(self, s, i):
        self.log_text.config(state=tk.NORMAL)
        msg = f"[{i+1}] VA:{s['virtual_addr']} → PG:{s['page']} OFF:{s['offset']} → "
        tag = "hit" if s["hit"] else "miss"
        result_str = "✓ HIT" if s["hit"] else "✗ MISS"
        self.log_text.insert(tk.END, msg, "")
        self.log_text.insert(tk.END, result_str, tag)
        extra = f"  FR:{s['frame']} PA:{s['phys_addr']}"
        if s["replaced"] is not None:
            extra += f"  [EVICTED PG:{s['replaced']}]"
            self.log_text.insert(tk.END, extra + "\n", "replace")
        else:
            self.log_text.insert(tk.END, extra + "\n", "")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = TLBApp()
    app.mainloop()
