Scenario	Success	Served by	p50	p95	Notes
A. Baseline	20/20 (100%)	fast ×20	479 ms	616 ms	first request about 2.9 s (warm-up)
B. Groq down	20/20 (100%)	smart ×20	1228 ms	6144 ms	breaker opened after 3 failures; then about 1.2 s
C. Groq + OpenAI down	20/20 (100%)	local ×20	3946 ms	18084 ms	spikes every ~30 s = recovery checks
D. All down	0/20	502 ×20	12 ms	19838 ms	after breakers open, 502 in about 10 ms