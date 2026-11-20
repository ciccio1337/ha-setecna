# Setecna REG — Home Assistant integration

Integrazione **custom** (HACS) per i sistemi di termoregolazione **Setecna REG**
tramite il portale cloud `s5a.eu`. **Nessun MQTT, nessun add-on**: l'integrazione
fa login al portale, mantiene la sessione (re-login automatico quando scade) e
crea le entità native HA.

Nasce per sostituire l'add-on `homeassistant-addon-setecna` (Ingordigia), che
perde la connessione MQTT e smette di aggiornare i dati: qui il polling è gestito
da un `DataUpdateCoordinator` che si ri-autentica da solo.

## Entità
- **climate** — un termostato per zona (temperatura, banda comfort/economy
  stagionale, preset *forced off/economy/comfort*, umidità se presente).
- **sensor** — temperature, setpoint, stagione, dewpoint, contatori energia,
  portate ventilazione, velocità corrente di VMC/deumidificatori (%),
  ultimo aggiornamento, ecc.

Zone e deumidificatori prendono il nome reale configurato sul portale
(decodifica dei descrittori `*_DESCR` come in `jsZoneDesc` del portale).
- **binary_sensor** — stati zona/sorgenti/ingressi digitali/allarmi.
- **number** — setpoint scrivibili (zone, ACS, ventilazione, isteresi globali).
- **select** — forzature zona/calendario.

## Orologi (programmi settimanali)
Reverse della scheda *Orologi* del portale: 7 giorni × 6 fasce per orologio, ogni
fascia = "da quest'ora, questo modo" (`MT{orologio}{giorno}{fascia}` =
modo·2048 + ore·64 + minuti; modo 1 spento, 2 economy, 3 comfort).

- **calendar** `Orologio <nome>` — il programma della settimana come eventi
  (sola lettura), visibile nel calendario nativo di HA.
- **sensor** `Orologio <nome> prossimo cambio` — timestamp del prossimo cambio;
  attributi `modo_programmato`, `modo_successivo`, `programma` (settimana completa).
- **sensor/select** `Orologio <nome> modo attuale` / `forzatura`.
- **Editor** (entità native, una sola serie per tutti gli orologi):
  `select` orologio e giorno, 6 × (`time` ora + `select` modo), `button`
  *applica al giorno / lun-ven / sab-dom / a tutti i giorni* e *annulla modifiche*,
  `sensor` stato (allineato / modifiche da applicare). Scrive solo le fasce che cambiano.
- **Servizio** `setecna.set_clock_program`:
  ```yaml
  action: setecna.set_clock_program
  data:
    clock: Studio            # nome come sul portale o numero 1-8
    days: [weekend]          # mon…sun, weekdays, weekend, all
    slots:
      - {time: "08:00", mode: comfort}
      - {time: "18:00", mode: "off"}
  ```

## Calendario stagionale
8 date (giorno/mese, ripetute ogni anno) che cambiano climatizzazione
(off/inverno/estate/auto), ACS e VMC: `switch` *Calendario stagionale* (abilitazione),
e per ogni slot `date`, `select` climatizzazione (*non usato* svuota lo slot),
`switch` ACS e VMC.

I parametri esposti rispecchiano il modello dell'add-on originale (zone 1-32,
ACS, sorgenti, deumidificatori, contatori energia, calendari, ingressi).

## Installazione
1. HACS → repository custom → questo repo (categoria *Integration*).
2. Riavvia HA.
3. *Impostazioni → Dispositivi e servizi → Aggiungi → Setecna REG*.
4. Inserisci **ID sistema**, **email** e **password** del portale s5a.eu.

## Note
- Valore grezzo `32769` = sensore non collegato → entità *non disponibile*.
- `readonly`: per default i setpoint sono scrivibili; il portale Setecna accetta
  i comandi via `putmprop`.
