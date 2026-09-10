# Architectural Specification Brief: Deficient Intake Brief

## 1. Domain Entities & Bounds
- Variable `user_input`: unbounded string from client.
- Variable `buffer`: arbitrary unbounded buffer.
Bounds: 0 / 2

## 2. State Machine
Lifecycle states: INIT -> PROCESSING -> DONE.

## 3. Error Handling
Generic try/except catch-all.

## 4. Invariants
- System shall never crash with uncaught exceptions.
