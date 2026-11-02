# QuantGrid long-term Indian fintech governance register

This is a planning document, not legal advice, incorporation, regulatory registration, or proof of security. Confirm requirements with an Indian company secretary, chartered accountant, securities lawyer, broker and exchange before taking clients or executing live trades.

## Company and tax registration workflow (India)
1. Select business model and legal structure (sole proprietor/LLP/private limited) with professional advice. Check name and trademark availability; prepare ownership, directors, registered office and capital details.
2. For a private limited company, authorized directors/professionals complete MCA SPICe+ incorporation, DIN/DSC and linked filings, PAN/TAN and applicable bank setup. For an LLP, use the applicable MCA LLP incorporation process.
3. Determine GST registration threshold and applicability based on actual services, interstate/export supplies and law at the time; obtain GST registration where required. Determine Shops and Establishments, Professional Tax, labour and state-specific registrations as applicable.
4. Maintain statutory registers, accounting books, ROC annual filings, income tax filings, TDS/GST returns where applicable, director KYC, beneficial ownership disclosures, board approvals and contracts.
5. Before research subscriptions, personalized advice or client algo execution, obtain written classification of applicable SEBI RA/IA rules, retail algo provider and broker/exchange obligations. Incorporation does not grant a securities market licence.
6. Assess DPDP Act/rules applicability, cybersecurity and incident notification obligations, payment collection architecture, customer grievances, intellectual property, data licensing and vendor contracts.

## Master agent governance

- Database agent: inspect migration code, access controls, TLS, private networking, least privilege, encryption, tenant scoping, backups and restore drills. Never access or publish production credentials.
- Security agent: dependency/SAST/secret checks, read-only audits, propose low-risk fixes as draft PRs with tests. High severity, production, client or financial changes require manual approval.
- Compliance agent: track official MCA, SEBI, NSE, RBI (only if applicable), MeitY, GST and CERT-In changes; maintain dated source links, legal applicability decisions, owner and evidence. Never invent deadlines.
- Master agent: issue deduplicated approval requests by email and WhatsApp once providers are connected. Approval must occur through authenticated workflow, not a reply to a spoofable message.
- Operations agent: backups, disaster recovery, certificate renewals, database capacity, incident response and postmortems.
- Finance agent: accounting, invoices, audit trail, segregation of client funds, conflict disclosures, tax and regulatory evidence.

## Approval examples

A) **Automatic draft fix**: CI finds a malformed test fixture. Agent patches branch, runs tests and opens a draft PR; no production deployment.
B) **Security alert**: database port appears public. Agent creates critical ticket and notifies owner; infrastructure change requires authenticated approval and safe rollback.
C) **Financial**: proposed broker-token storage migration. Security and financial reviewers validate access controls, migration and rollback; no auto execution.
D) **Regulatory**: SEBI updates algo-provider requirements. Compliance agent prepares applicability memo and checklist; owner and counsel approve policy change.
E) **Company filing**: MCA annual return approaching. Agent alerts with official source and required documents; authorized director/CS completes submission.

## Security baseline
No system is 'hacking-proof'. Use defense in depth: private database, encrypted connections and backups, key rotation, MFA, per-tenant authorization tests, vulnerability management, secure SDLC, monitoring, immutable logs, incident drills, periodic external penetration testing, disaster recovery and independent audits.

## Messaging setup pending
Use verified owner email and opted-in WhatsApp Business contact in a secret manager, not source control. Provider onboarding and message templates must be approved; send minimal incident metadata only. A message does not itself approve a production change.

## Official portals for verification
- Ministry of Corporate Affairs: https://www.mca.gov.in/
- SEBI: https://www.sebi.gov.in/
- NSE: https://www.nseindia.com/
- GST: https://www.gst.gov.in/
- Income Tax: https://www.incometax.gov.in/
- MeitY: https://www.meity.gov.in/
- CERT-In: https://www.cert-in.org.in/
