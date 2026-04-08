"""
TLB Simulator — FastAPI Backend
Run: uvicorn main:app --reload
Docs: http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from collections import OrderedDict

app = FastAPI(title="TLB Simulator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── MODELS ───────────────────────────────────────────────────────────────────

class SimRequest(BaseModel):
    virtual_addresses: List[int] = Field(
        ..., example=[0, 512, 1024, 1536, 2048, 512, 1024, 3072]
    )
    page_size: int  = Field(256, gt=0, description="Page size in bytes (power of 2)")
    num_pages: int  = Field(8,   gt=0, description="Number of virtual pages")
    tlb_size:  int  = Field(4,   gt=0, description="Number of TLB entries")
    policy:    str  = Field("FIFO", description="Replacement policy: FIFO or LRU")
    tlb_time:  int  = Field(10,  gt=0, description="TLB access time in ns")
    mem_time:  int  = Field(100, gt=0, description="Main memory access time in ns")

class StepRequest(BaseModel):
    virtual_address: int
    page_size: int  = Field(256, gt=0)
    num_pages: int  = Field(8,   gt=0)
    tlb_size:  int  = Field(4,   gt=0)
    policy:    str  = Field("FIFO")
    tlb_time:  int  = Field(10,  gt=0)
    mem_time:  int  = Field(100, gt=0)
    # Pass current TLB and page table state for stateless stepping
    tlb_state:   Optional[List[Dict]] = Field(None, description="Current TLB [{page,frame}]")
    page_table:  Optional[Dict[str, int]] = Field(None, description="Current page table")
    next_frame:  Optional[int] = Field(0, description="Next frame to allocate")
    fifo_order:  Optional[List[int]] = Field(None, description="FIFO queue state")
    lru_order:   Optional[List[int]] = Field(None, description="LRU order state")

class AddressResult(BaseModel):
    index:        int
    virtual_addr: int
    page:         int
    offset:       int
    hit:          bool
    frame:        int
    phys_addr:    int
    replaced:     Optional[int]
    tlb_before:   List[Dict]
    tlb_after:    List[Dict]

class SummaryResult(BaseModel):
    total_accesses: int
    tlb_hits:       int
    tlb_misses:     int
    hit_ratio:      float
    miss_ratio:     float
    effective_access_time: float
    eat_formula:    str

class SimResponse(BaseModel):
    results:  List[AddressResult]
    summary:  SummaryResult
    page_table_final: Dict[str, int]
    tlb_final: List[Dict]

class StepResponse(BaseModel):
    result:     AddressResult
    page_table: Dict[str, int]
    tlb_state:  List[Dict]
    next_frame: int
    fifo_order: List[int]
    lru_order:  List[int]

# ─── SIMULATOR ────────────────────────────────────────────────────────────────

class TLBSimulator:
    def __init__(self, page_size, num_pages, tlb_size, policy, tlb_time, mem_time):
        self.page_size  = page_size
        self.num_pages  = num_pages
        self.tlb_size   = tlb_size
        self.policy     = policy.upper()
        self.tlb_time   = tlb_time
        self.mem_time   = mem_time

        self.page_table: Dict[int, int] = {}
        self.tlb = OrderedDict()        # page -> frame
        self.next_frame = 0

    def _tlb_insert(self, page, frame):
        replaced = None
        if len(self.tlb) >= self.tlb_size:
            evict = next(iter(self.tlb))  # oldest for both FIFO and LRU
            replaced = evict
            del self.tlb[evict]
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

    def _tlb_snapshot(self):
        return [{"page": p, "frame": f} for p, f in self.tlb.items()]

    def access(self, virtual_addr, idx=0):
        page   = virtual_addr // self.page_size
        offset = virtual_addr % self.page_size

        if page >= self.num_pages:
            raise ValueError(f"Page {page} out of range (max {self.num_pages - 1})")

        tlb_before = self._tlb_snapshot()
        entry = self.tlb.get(page)
        hit = entry is not None
        replaced = None

        if hit:
            frame = entry
            if self.policy == "LRU":
                self._update_lru(page)
        else:
            frame = self._alloc_frame(page)
            replaced = self._tlb_insert(page, frame)

        phys_addr = frame * self.page_size + offset
        tlb_after = self._tlb_snapshot()

        return AddressResult(
            index=idx,
            virtual_addr=virtual_addr,
            page=page,
            offset=offset,
            hit=hit,
            frame=frame,
            phys_addr=phys_addr,
            replaced=replaced,
            tlb_before=tlb_before,
            tlb_after=tlb_after,
        )

    def compute_summary(self, results: List[AddressResult]) -> SummaryResult:
        n      = len(results)
        hits   = sum(1 for r in results if r.hit)
        misses = n - hits
        hr     = hits / n if n else 0.0
        mr     = 1 - hr
        eat    = hr * (self.tlb_time + self.mem_time) + \
                 mr * (self.tlb_time + 2 * self.mem_time)
        formula = (
            f"EAT = {hr:.2f}×({self.tlb_time}+{self.mem_time}) + "
            f"{mr:.2f}×({self.tlb_time}+2×{self.mem_time}) = {eat:.2f} ns"
        )
        return SummaryResult(
            total_accesses=n,
            tlb_hits=hits,
            tlb_misses=misses,
            hit_ratio=round(hr, 4),
            miss_ratio=round(mr, 4),
            effective_access_time=round(eat, 4),
            eat_formula=formula,
        )

# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "TLB Simulator API v1.0"}

@app.post("/simulate", response_model=SimResponse, tags=["Simulation"])
def simulate(req: SimRequest):
    """
    Run a full TLB simulation for a list of virtual addresses.
    Returns per-address results, page table snapshot, TLB state, and summary statistics.
    """
    if req.policy.upper() not in ("FIFO", "LRU"):
        raise HTTPException(400, "policy must be 'FIFO' or 'LRU'")
    if not req.virtual_addresses:
        raise HTTPException(400, "virtual_addresses must not be empty")

    sim = TLBSimulator(
        req.page_size, req.num_pages, req.tlb_size,
        req.policy, req.tlb_time, req.mem_time
    )

    results = []
    for i, va in enumerate(req.virtual_addresses):
        try:
            r = sim.access(va, i)
        except ValueError as e:
            raise HTTPException(422, str(e))
        results.append(r)

    summary = sim.compute_summary(results)
    pt_str  = {str(k): v for k, v in sim.page_table.items()}

    return SimResponse(
        results=results,
        summary=summary,
        page_table_final=pt_str,
        tlb_final=sim._tlb_snapshot(),
    )

@app.post("/simulate/step", response_model=StepResponse, tags=["Simulation"])
def simulate_step(req: StepRequest):
    """
    Process ONE virtual address in stateless step mode.
    Pass current TLB state, page table, fifo/lru order, and next_frame back each time.
    """
    if req.policy.upper() not in ("FIFO", "LRU"):
        raise HTTPException(400, "policy must be 'FIFO' or 'LRU'")

    sim = TLBSimulator(
        req.page_size, req.num_pages, req.tlb_size,
        req.policy, req.tlb_time, req.mem_time
    )

    # Restore state
    if req.page_table:
        sim.page_table = {int(k): v for k, v in req.page_table.items()}
    if req.next_frame is not None:
        sim.next_frame = req.next_frame

    if req.tlb_state:
        if req.policy.upper() == "LRU" and req.lru_order:
            order = req.lru_order
        elif req.fifo_order:
            order = req.fifo_order
        else:
            order = [e["page"] for e in req.tlb_state]
        tlb_map = {e["page"]: e["frame"] for e in req.tlb_state}
        for pg in order:
            if pg in tlb_map:
                sim.tlb[pg] = tlb_map[pg]

    try:
        result = sim.access(req.virtual_address, 0)
    except ValueError as e:
        raise HTTPException(422, str(e))

    pt_str      = {str(k): v for k, v in sim.page_table.items()}
    fifo_order  = list(sim.tlb.keys())
    lru_order   = list(sim.tlb.keys())

    return StepResponse(
        result=result,
        page_table=pt_str,
        tlb_state=sim._tlb_snapshot(),
        next_frame=sim.next_frame,
        fifo_order=fifo_order,
        lru_order=lru_order,
    )

@app.get("/simulate/sample", tags=["Simulation"])
def get_sample():
    """Returns a ready-to-use sample simulation request."""
    return {
        "virtual_addresses": [0, 512, 1024, 1536, 2048, 512, 1024, 3072, 4096, 512],
        "page_size": 256,
        "num_pages": 8,
        "tlb_size": 4,
        "policy": "LRU",
        "tlb_time": 10,
        "mem_time": 100
    }

@app.get("/policies", tags=["Info"])
def get_policies():
    return {
        "supported_policies": [
            {"name": "FIFO", "description": "First In First Out — evicts oldest TLB entry"},
            {"name": "LRU",  "description": "Least Recently Used — evicts least recently accessed entry"},
        ]
    }
