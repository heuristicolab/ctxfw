graph TD
    subgraph Ingestion ["Ingesta Perimetral O(1) < 2.0ms"]
        ClientReq["Cliente / Webhook API: Inbound Payload"] --> Sensor["PerimeterValidator: validate_ticket"]
        Sensor -- "Validado (< 2.0ms)" --> FSM["SlaGovernanceEngine: process_order_async"]
        Sensor -- "Inyeccion / Malformado" --> Reject["HTTP 422 Unprocessable Entity"]
    end
    subgraph Core ["AI Core & Bounded Contexts"]
        FSM --> Engine["DomainProcessingEngine: Enterprise Invariant Engine"]
        Engine --> SettlementWorker["Settlement & Ledger Worker: Atomic Lock"]
        SettlementWorker --> WAL[("PostgreSQL / SQLite WAL: orders, domain_records, audits")]
    end
    subgraph Customs ["Aduana HITL & Notificaciones"]
        WAL --> OperatorHUD["Torre de Control Operator HUD: /admin/orders"]
        OperatorHUD -- "Sello Criptografico SHA-256" --> DeliverState["DELIVERED State"]
        DeliverState --> Dispatcher["TransactionalNotificationDispatcher: Magic Links"]
    end
    style Ingestion fill:#0a0a0a,stroke:#00ff66,stroke-width:2px
    style Core fill:#050505,stroke:#22d3ee,stroke-width:2px
    style Customs fill:#080808,stroke:#ffaa00,stroke-width:2px