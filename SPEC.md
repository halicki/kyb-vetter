# SPEC: kyb-vetter — platforma do weryfikacji polskich firm dla agentów AI

Budujemy produkt (docelowo firmę): hostowany serwer MCP + REST API do weryfikacji kontrahentów w polskich rejestrach publicznych, z dowodem weryfikacji (audit trail). Użytkownik niczego nie instaluje — dodaje URL jako connector w Claude, ChatGPT lub Gemini, albo woła REST API. Pozycjonowanie: "KYB / counterparty verification for AI agents" w środowiskach regulowanych. To też mój projekt do nauki (MCP, Terraform, GCP), więc jakość inżynierska i zrozumienie decyzji są ważniejsze niż tempo.

Kod, docstringi, commity, README i ADR-y po angielsku. Ze mną rozmawiaj po polsku.

## Nazwa

- Robocza nazwa projektu i repo: `kyb-vetter` (pakiety Pythona: `kyb_vetter_*`). Marka produktu NIE jest jeszcze ustalona.
- Nazwa musi żyć w JEDNYM miejscu na warstwę: zmienna `project_name` w Terraformie (prefiks wszystkich zasobów GCP), jedna stała/konfiguracja w kodzie, nazwa w `pyproject.toml`. Nigdzie nie hardkoduj "kyb-vetter" w stringach, URL-ach ani nazwach zasobów — rebranding ma być zmianą kilku linijek.
- Domena i nazwa connectora pochodzą z konfiguracji (zmienna `domain`), nie z kodu.

## Tryb pracy

- Pracuj MILESTONE'AMI z listy niżej. Po każdym: STOP, pokaż co powstało, wyjaśnij 3–5 kluczowych decyzji (dlaczego, jakie alternatywy, koszty), czekaj na moje OK.
- Decyzje architektoniczne zapisuj jako ADR w `docs/adr/` (krótkie: kontekst, decyzja, konsekwencje).
- Na starcie zapytaj mnie o to, czego nie wiesz: projekt GCP / billing account, domena, wybór IdP, region (domyślnie europe-central2 — Warszawa).
- Nie implementuj rzeczy z backlogu. Pytaj przed dodaniem zależności spoza stacku.
- Testy NIGDY nie uderzają w prawdziwe API rządowe (limity, blokada IP). HTTP mockuj (respx). Testy live tylko z markerem `live`, domyślnie wyłączone.
- Przed użyciem jakiejkolwiek biblioteki/API sprawdź aktualną dokumentację zamiast polegać na pamięci (MCP Python SDK, specyfikacja MCP 2026-07-28, API rządowe, providery Terraform).

## Stack

- Python: najnowszy stabilny (3.15). Sprawdź, czy wszystkie zależności mają wheele pod 3.15; jeśli nie — 3.14 i zapisz to w ADR.
- Monorepo na uv workspaces. ruff, pyright (strict w core), pytest + pytest-asyncio + respx, pre-commit.
- MCP: oficjalny Python SDK (FastMCP), zgodność ze specyfikacją 2026-07-28 (bezstanowy Streamable HTTP, `server/discover`). Sprawdź, czy SDK już ją wspiera, i opisz luki.
- REST: FastAPI. Modele: pydantic v2. HTTP: httpx async.
- DB: Postgres (lokalnie docker compose; w chmurze Cloud SQL vs Neon — porównaj koszt i złożoność, zaproponuj ADR). SQLAlchemy 2 async + Alembic.
- Infra: GCP + Terraform. Cloud Run (service: MCP+API; job: worker), Artifact Registry, Secret Manager, Cloud Scheduler, GCS (także remote state Terraforma), Cloud Logging/Trace. CI/CD: GitHub Actions z Workload Identity Federation (zero kluczy service account w repo). Budżet i alert kosztów w Terraformie.

## Struktura (propozycja do weryfikacji)

```
kyb-vetter/
  packages/core/      # domena: klienci rejestrów, walidacja NIP/REGON/NRB, modele, limity, audyt
  apps/mcp/           # serwer MCP (stdio lokalnie, Streamable HTTP w chmurze)
  apps/api/           # REST API (FastAPI) na tym samym core
  apps/worker/        # joby: codzienny plik płaski MF, później listy sankcyjne
  infra/terraform/    # modules/ + envs/dev, envs/prod
  evals/              # zestawy ewaluacyjne dla narzędzi MCP
  docs/adr/
  SPEC.md             # ten plik
```

Logika biznesowa żyje WYŁĄCZNIE w `core`. MCP i REST to cienkie adaptery.

## Źródła danych

1. Biała lista VAT (MF), bez klucza: https://wl-api.mf.gov.pl (sprawdź środowisko testowe wl-test.mf.gov.pl).
   - search (/api/search/nip/{nip}, /api/search/nips/{lista do 30}) — 100 zapytań/dzień/IP.
   - check (/api/check/nip/{nip}/bank-account/{nrb}) — 5000/dzień.
   - Po przekroczeniu: blokada IP do północy. Hostowany serwer = jedno IP dla wszystkich użytkowników, więc limity to problem architektoniczny, nie szczegół.
   - `requestId` w odpowiedzi = dowód weryfikacji wobec urzędu skarbowego. Przechowujemy go.
   - PLIK PŁASKI MF: codzienny plik z zahashowanymi parami NIP+rachunek do masowej weryfikacji offline. Przeczytaj oficjalną specyfikację algorytmu hashowania i masek rachunków wirtualnych. To jest podstawa `check_bank_account` w wersji hostowanej.
2. KRS (MS), bez klucza, ~2 req/s: https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{krs}?rejestr=P|S&format=json. Szuka tylko po numerze KRS (bierzemy go z białej listy). Dane osób zanonimizowane. Dane objęte ustawą o otwartych danych — dozwolone ponowne wykorzystanie.
3. CEIDG (JDG): https://dane.biznes.gov.pl/api/ceidg/v3/firmy, JWT Bearer. To dane osób fizycznych → RODO. W MVP: tylko pass-through, ZERO zapisu w bazie, opcjonalne (bez tokena narzędzie działa i mówi, że CEIDG pominięto).

## Projekt narzędzi MCP

- Tylko TOOLS (ChatGPT nie obsługuje prompts/resources z serwerów zdalnych). Wszystko tylko do odczytu.
- Docstring = prompt dla modelu: kiedy użyć, co zwraca, ograniczenia. Zwracamy zwięzłe modele, nie surowy JSON z API.
- Dane z rejestrów (nazwy firm, adresy) to NIEZAUFANE dane — nie mogą sterować modelem; testy prompt injection obowiązkowe.
- Narzędzia MVP: `verify_company(nip)`, `check_bank_account(nip, account)`, `verification_history(nip)`. Każde wywołanie zapisuje się w audycie (user, narzędzie, wejście, requestId, timestamp, SHA-256 odpowiedzi, źródła).
- Zero printów na stdout w trybie stdio.

## Auth

- MCP: OAuth zgodnie ze specyfikacją MCP (Protected Resource Metadata RFC 9728, CIMD + DCR jako fallback, PKCE, refresh tokeny). NIE piszemy własnego serwera autoryzacji — porównaj zewnętrzne IdP (np. WorkOS AuthKit, Auth0, Stytch, Descope, Google Identity Platform) pod kątem: zgodność z MCP auth, koszt na start, EU data residency. ADR.
- REST: klucze API per użytkownik (hashowane w bazie).
- Rate limiting i limity per użytkownik niezależnie od limitów MF.
- Wymagany publiczny TLS (Gemini Enterprise odrzuca self-signed).

## Milestone'y

0. ADR-y startowe + szkielet monorepo `kyb-vetter` + tooling + CI (lint, typy, testy). Konfiguracja nazwy w jednym miejscu.
1. Core: walidacja NIP/NRB (lokalnie, przed API — oszczędza limit), klient białej listy (search, check), klient KRS, modele domenowe, mapowanie błędów WL-1xx na błędy domenowe.
2. Serwer MCP lokalnie (stdio) z `verify_company` i `check_bank_account` (na razie API check), instrukcja testu w MCP Inspector i Claude Desktop. Pierwsze evale.
3. Persistence: Postgres + Alembic, strażnik limitów MF (twarda odmowa przy 90/100 i 4800/5000 na całe IP), audit log, `verification_history`.
4. Infra dev: Terraform (remote state w GCS, Artifact Registry, Cloud Run service, baza, Secret Manager, WIF dla GitHub Actions, budżet+alert). Wszystkie zasoby z prefiksem `var.project_name`. Deploy MCP przez Streamable HTTP pod publicznym HTTPS. Pipeline: push na main → testy → build → deploy na dev.
5. Worker: Cloud Run Job + Cloud Scheduler — codzienne pobranie pliku płaskiego MF, weryfikacja integralności, załadowanie do bazy/GCS; `check_bank_account` przełącza się na plik płaski (API jako fallback w ramach limitu).
6. Auth: OAuth dla MCP przez wybrany IdP, klucze API dla REST, rate limiting per user. Test connectorów: Claude (custom connector), ChatGPT (Developer Mode), Gemini (custom app). Udokumentuj kroki dla każdego.
7. REST API (FastAPI) na tym samym core + OpenAPI.
8. Hardening: strukturalne logi + tracing (OpenTelemetry), evale w CI, testy prompt injection, retencja danych w audycie (polityka RODO), środowisko prod w Terraformie.

## Backlog (NIE implementować bez mojej decyzji)

Listy sankcyjne (MSWiA, skonsolidowana lista UE), lista ostrzeżeń KNF, raport KYB jako PDF, CEIDG z cache, płatności (Stripe), landing page, regulamin i polityka prywatności, docelowa marka i domena (rebranding z `kyb-vetter`), zgłoszenie do katalogów connectorów (Anthropic, OpenAI), interaktywne widgety (MCP Apps).

## Ustalenia (2026-10-22)

- GCP: nowy projekt tworzony przez Terraform; billing account podany przed M4.
- Domena: placeholder do M6.
- Region: `europe-west1` (ADR-0005).
- IdP: decyzja w ADR przed M6.
- Type checker: `ty` zamiast pyright (decyzja 2026-10-22, ADR-0006).
- Biała lista: API przeniesione 15.10.2026 na `https://wykazpodatnikowvat.mf.gov.pl` (test: `wykazpodatnikowvat-test.mf.gov.pl`); `wl-api.mf.gov.pl` działa tylko do 1.12.2026. Nowy endpoint WL2 `/api2/status/nip/{nip}` (limit 50 000/dzień) jest głównym źródłem statusu VAT (ADR-0009).
- KRS: rejestr `P`, przy 404 próba `S` (ADR-0010).
- TDD obowiązuje dla każdej funkcji w `core`; pokrycie 100% jest bramką w CI.
- M2 (2026-10-22): evale deterministyczne w `evals/` (CI), bez LLM; `verify_company` zwraca skondensowany profil (ADR-0011/0012); serwer MCP przez `python -m kyb_vetter_mcp`.
- M3 (2026-10-22): Postgres przez `APP_DATABASE_URL` (bez URL fallback in-memory dla stdio); testy DB na compose lokalnie i service container w CI; chmura: Neon (ADR-0014); cache per `(identyfikator, dzień)`; strażnik limitów 90/4800/45000 (ADR-0013).
- M4 (2026-10-23): dev tylko przez IAM (bez `allUsers`) do M6; dev używa hosta testowego MF; Neon przez `kislerdm/neon` 0.18.0 do czasu publikacji `neondatabase/neon`; Terraform lokalnie, CI tylko roluje obraz (ADR-0015).
- M5 (2026-10-23): indeks pliku płaskiego jako 16-bajtowe prefiksy w GCS (nie Postgres); nowe zależności py7zr, ijson, google-cloud-storage; chybienie w pliku zawsze potwierdzane w API (ADR-0016).
