"""
tests/test_polyglot_pruner.py — Verification Matrix for Tree-sitter Polyglot Pruning
Validates concrete syntax tree (CST) pruning for TypeScript/JavaScript, Go, and Java,
preserving signatures, interfaces, and type schemas while stubbing method bodies.
"""
from __future__ import annotations

import pytest

from contracts import (
    DeterministicContextPruner,
    LocalSemanticCache,
    OptimizationRequestDTO,
    PruningDepth,
)
from polyglot_pruner import SupportedLanguage, TreeSitterContextPruner


SAMPLE_TYPESCRIPT_CODE = """
export interface UserRecord {
    id: string;
    email: string;
    isActive: boolean;
}

export type AccountStatus = "active" | "suspended" | "pending";

export function computeAccountBalance(base: number, adjustments: number[]): number {
    const totalAdjustments = adjustments.reduce((acc, curr) => acc + curr, 0);
    const balance = base + totalAdjustments;
    return balance;
}

export class TransactionEngine {
    private readonly version: string = "2.0";

    public processPayment(record: UserRecord, amount: number): boolean {
        console.log("Authorizing", amount, "for", record.id);
        const fee = amount * 0.02;
        return amount > fee;
    }
}
"""

SAMPLE_GO_CODE = """package banking

type LedgerEntry struct {
    EntryID     string
    Amount      float64
    IsCertified bool
}

type BankAccount interface {
    Deposit(amount float64) error
    Withdraw(amount float64) (float64, error)
}

func CalculateNetReserves(entries []LedgerEntry) float64 {
    var total float64
    for _, e := range entries {
        total += e.Amount
    }
    return total
}

func (l *LedgerEntry) ValidateEntry() bool {
    checksum := len(l.EntryID) * 42
    return checksum > 0 && l.Amount >= 0.0
}
"""

SAMPLE_JAVA_CODE = """package com.heuristico.gateway;

public class PaymentSettlementService {
    private final String gatewayEndpoint;

    public PaymentSettlementService(String endpoint) {
        this.gatewayEndpoint = endpoint;
        System.out.println("Initialized with " + endpoint);
    }

    public boolean executeBatchSettlement(String batchId, double totalAmount) {
        double auditRatio = totalAmount / 1000.0;
        int check = (int) auditRatio * 7;
        return check > 0;
    }
}
"""


def test_typescript_pruning_preserves_interfaces_and_stubs_bodies():
    """Asserts that TypeScript AST retains interfaces, types, signatures, and stubs bodies with { /* ... */ }."""
    req = OptimizationRequestDTO(
        source_code=SAMPLE_TYPESCRIPT_CODE,
        language=SupportedLanguage.TYPESCRIPT,
        depth=PruningDepth.INTERFACE,
    )
    pruned, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)

    # Invariants: Interfaces and Types must remain intact
    assert "export interface UserRecord {" in pruned
    assert "id: string;" in pruned
    assert "export type AccountStatus = \"active\" | \"suspended\" | \"pending\";" in pruned

    # Invariants: Signatures must be preserved
    assert "export function computeAccountBalance(base: number, adjustments: number[]): number" in pruned
    assert "public processPayment(record: UserRecord, amount: number): boolean" in pruned

    # Invariants: Internal logic must be stripped and replaced with typed block comment
    assert "{ /* ... */ }" in pruned
    assert "adjustments.reduce" not in pruned
    assert "console.log" not in pruned

    assert pct >= 20.0
    assert saved > 0
    assert ms <= 50.0


def test_go_pruning_preserves_structs_and_stubs_functions():
    """Asserts that Go AST retains structs, interfaces, package definitions, and inserts panic stubs."""
    req = OptimizationRequestDTO(
        source_code=SAMPLE_GO_CODE,
        language=SupportedLanguage.GO,
        depth=PruningDepth.INTERFACE,
    )
    pruned, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)

    # Invariants: Package, structs, and interfaces preserved
    assert "package banking" in pruned
    assert "type LedgerEntry struct {" in pruned
    assert "type BankAccount interface {" in pruned

    # Invariants: Signatures preserved
    assert "func CalculateNetReserves(entries []LedgerEntry) float64" in pruned
    assert "func (l *LedgerEntry) ValidateEntry() bool" in pruned

    # Invariants: Method bodies replaced with panic stubs
    assert '{ panic("not implemented") }' in pruned
    assert "for _, e := range entries" not in pruned
    assert "checksum := len(l.EntryID)" not in pruned

    assert pct >= 15.0
    assert saved > 0


def test_java_pruning_preserves_classes_and_stubs_methods():
    """Asserts that Java AST retains classes, package headers, and replaces bodies with throw stubs."""
    req = OptimizationRequestDTO(
        source_code=SAMPLE_JAVA_CODE,
        language=SupportedLanguage.JAVA,
        depth=PruningDepth.INTERFACE,
    )
    pruned, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)

    # Invariants: Package and class definitions preserved
    assert "package com.heuristico.gateway;" in pruned
    assert "public class PaymentSettlementService {" in pruned
    assert "private final String gatewayEndpoint;" in pruned

    # Invariants: Signatures preserved
    assert "public PaymentSettlementService(String endpoint)" in pruned
    assert "public boolean executeBatchSettlement(String batchId, double totalAmount)" in pruned

    # Invariants: Bodies replaced with UnsupportedOperationException
    assert "{ throw new UnsupportedOperationException(); }" in pruned
    assert "System.out.println" not in pruned
    assert "auditRatio * 7" not in pruned

    assert pct >= 20.0
    assert saved > 0


def test_polyglot_cache_key_differentiation():
    """Asserts that cache keys incorporate the language identifier to prevent cross-language collisions."""
    code_common = "function test() { return 1; }"
    key_py = LocalSemanticCache.generate_key(code_common, "v2.0.0", False, language="python")
    key_ts = LocalSemanticCache.generate_key(code_common, "v2.0.0", False, language="typescript")
    key_go = LocalSemanticCache.generate_key(code_common, "v2.0.0", False, language="go")
    key_java = LocalSemanticCache.generate_key(code_common, "v2.0.0", False, language="java")

    assert key_py != key_ts
    assert key_ts != key_go
    assert key_go != key_java
    assert len({key_py, key_ts, key_go, key_java}) == 4
