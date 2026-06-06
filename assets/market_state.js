// Market status chip — shows whether NSE is live, pre-market, or closed.
// REVIEW EACH DECEMBER — NSE publishes next year's holiday list in November.
// Source: https://www.nseindia.com/regulations/holiday-master
const NSE_HOLIDAYS_2026 = [
  '2026-01-26', // Republic Day
  '2026-03-02', // Mahashivratri
  '2026-03-25', // Holi
  '2026-03-30', // Id-Ul-Fitr (Ramzan)
  '2026-04-02', // Shri Ram Navami
  '2026-04-03', // Good Friday
  '2026-04-14', // Dr. Ambedkar Jayanti
  '2026-04-30', // Buddha Pournima
  '2026-06-27', // Bakri Id
  '2026-07-29', // Muharram
  '2026-08-15', // Independence Day
  '2026-08-26', // Ganesh Chaturthi
  '2026-10-02', // Gandhi Jayanti
  '2026-10-22', // Dussehra
  '2026-11-11', // Diwali (Laxmi Pujan)
  '2026-11-12', // Diwali (Balipratipada)
  '2026-11-25', // Guru Nanak Jayanti
  '2026-12-25', // Christmas
];

function getISTDate() {
  var now = new Date();
  // IST = UTC + 5:30
  var istOffset = 5 * 60 + 30;
  var istMs = now.getTime() + (istOffset + now.getTimezoneOffset()) * 60000;
  return new Date(istMs);
}

function isMarketOpen() {
  var ist = getISTDate();
  var day = ist.getDay(); // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;

  var dateStr = ist.toISOString().slice(0, 10);
  if (NSE_HOLIDAYS_2026.includes(dateStr)) return false;

  var h = ist.getHours(), m = ist.getMinutes();
  var totalMin = h * 60 + m;
  return totalMin >= 9 * 60 + 15 && totalMin < 15 * 60 + 30;
}

function isPreMarket() {
  var ist = getISTDate();
  var day = ist.getDay();
  if (day === 0 || day === 6) return false;
  var dateStr = ist.toISOString().slice(0, 10);
  if (NSE_HOLIDAYS_2026.includes(dateStr)) return false;
  var totalMin = ist.getHours() * 60 + ist.getMinutes();
  return totalMin < 9 * 60 + 15;
}

function getMinutesToOpen() {
  var ist = getISTDate();
  var openMin = 9 * 60 + 15;
  var nowMin = ist.getHours() * 60 + ist.getMinutes();
  var diff = openMin - nowMin;
  var h = Math.floor(diff / 60);
  var m = diff % 60;
  return h > 0 ? (h + 'h ' + m + 'm') : (m + 'm');
}

function updateMarketChip() {
  var chip = document.getElementById('market-status-chip');
  if (!chip) return;

  if (isMarketOpen()) {
    chip.textContent = '● MARKET LIVE';
    chip.className = 'market-live';
  } else if (isPreMarket()) {
    chip.textContent = '🌅 Opens in ' + getMinutesToOpen();
    chip.className = 'market-pre';
  } else {
    chip.textContent = '○ Market closed';
    chip.className = 'market-closed';
  }
}

updateMarketChip();
setInterval(updateMarketChip, 30000); // update every 30s
