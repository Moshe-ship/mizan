"""Adapters that emit Mizan Receipts from inside real agent runtimes.

The Receipt is the product; an adapter is only proof that Receipts can sit
inside an actual agent framework. Each adapter module is import-safe with no
hard dependency on the framework it targets — install the matching extra
(e.g. ``pip install "mizan[openai]"``) to use it end to end.
"""
