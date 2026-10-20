/* Canlı maç anlatıcısı: her olay için spiker cümlesi (şablon; ücretli yapay zekâ yok).
   - Rakamlar ve isimler olaydan gelir; şablon sadece cümleyi kurar, uydurma yapmaz.
   - Cümle olayın kimliğinden seçilir: aynı olayı izleyen herkes aynı cümleyi görür.
   - İsimlerin ardına ek gelmez ("Muriqi'nin" / "Kanté'nin" ünlü uyumu derdi olmasın).
   Yer tutucular: {oyuncu} {asist} {dk} {skor} {fb} {rakip} {giren} {cikan} {takim}
   Tarayıcıda window.Commentary, Node'da (testler) module.exports. */
(function (root) {
    const T = {
        goal_fb: [
            "GOOOL! {oyuncu} ağları havalandırıyor, dakika {dk}! {skor}",
            "Ve top ağlarda! Fenerbahçe adına {oyuncu}, {dk}. dakika. {skor}",
            "Tribünler ayakta! {oyuncu} vuruyor ve gol! {skor}",
            "{dk}. dakikada sarı-lacivertliler golü buluyor, atan {oyuncu}! {skor}",
            "Kaleci çaresiz! {oyuncu} topu filelere gönderdi. {skor}",
            "İşte beklenen an! {oyuncu} ile gelen gol, {dk}. dakika. {skor}",
            "Gol, gol, gol! Fenerbahçe skoru değiştiriyor, golcü {oyuncu}. {skor}",
            "{oyuncu} affetmedi! Sarı-lacivertlilerden {dk}. dakikada gol. {skor}",
            "Tribünlerin sesi göklere çıkıyor! {oyuncu} ağları buldu. {skor}",
            "Müthiş bitiriş! {oyuncu}, dakika {dk}. {skor}",
            "Fenerbahçe atağı golle sonuçlandı, son vuruş {oyuncu}. {skor}",
            "Ve gol geliyor! {dk}. dakikada {oyuncu} sahnede. {skor}",
        ],
        goal_rival: [
            "Gol {rakip} tarafından, {dk}. dakikada {oyuncu} vurdu. {skor}",
            "Sarı-lacivertliler golü yedi: {oyuncu}, dakika {dk}. {skor}",
            "{rakip} skoru değiştirdi, golü atan {oyuncu}. {skor}",
            "Savunma bu kez geç kaldı, {oyuncu} affetmedi. {skor}",
            "{dk}. dakikada rakip golü buldu, {oyuncu} ile. {skor}",
            "Tribünler sessiz: {rakip} adına gol {oyuncu} ayağından. {skor}",
            "Kalemizde gol var, {dk}. dakika, atan {oyuncu}. {skor}",
            "Rakip fırsatı değerlendirdi, {oyuncu} ile gol. {skor}",
            "{oyuncu} vurdu, top ağlarda. {rakip} golü buldu. {skor}",
            "Beklenmedik an: {dk}. dakikada {rakip} sevinci, golcü {oyuncu}. {skor}",
        ],
        own_goal_for_fb: [
            "Kendi kalesine gol! {rakip} savunmasında {oyuncu} talihsiz, dakika {dk}. {skor}",
            "Fenerbahçe baskısı meyvesini verdi: {oyuncu} topu kendi ağlarına gönderdi. {skor}",
            "Talihsiz an! {oyuncu} kendi kalesine attı, {dk}. dakika. {skor}",
        ],
        own_goal_for_rival: [
            "Kendi kalemize gol! {oyuncu} talihsiz, dakika {dk}. {skor}",
            "Olmaz böyle şanssızlık: {oyuncu} topu kendi ağlarımıza gönderdi. {skor}",
            "Talihsiz bir sekme ve kendi kalemizde gol, {dk}. dakika. {skor}",
        ],
        assist: [
            "Pas {asist} imzalı.",
            "Asist: {asist}.",
            "{asist} harika bir pasla hazırladı.",
            "Asistte {asist} vardı.",
        ],
        penalty_goal_fb: [
            "Penaltıda hata yok! {oyuncu} topu ağlara yolladı, {dk}. dakika. {skor}",
            "Beyaz noktadan gol! {oyuncu} soğukkanlı, {skor}",
            "{oyuncu} penaltıyı gole çevirdi. {skor}",
        ],
        penalty_goal_rival: [
            "Penaltıdan gol: {oyuncu} kaleciyi yanılttı, {dk}. dakika. {skor}",
            "{rakip} penaltıyı gole çevirdi, atan {oyuncu}. {skor}",
            "Beyaz noktada {oyuncu} hata yapmadı. {skor}",
        ],
        yellow: [
            "{dk}. dakikada sarı kart: {oyuncu} ({takim}).",
            "Hakem cebine gitti, sarı kart {oyuncu} için. {dk}. dakika.",
            "{oyuncu} sarı kartla uyarıldı ({takim}).",
            "Sert müdahale, sarı kart! {oyuncu}, dakika {dk}.",
            "Kitapçığa bir isim daha: {oyuncu} sarı kart gördü.",
            "{takim} tarafında sarı kart, {oyuncu}. {dk}. dakika.",
            "Hakem affetmedi, {oyuncu} sarı kartla cezalandırıldı.",
            "Sarı kart çıktı: {oyuncu}, {dk}. dakika.",
            "{oyuncu} için sarı kart; bundan sonra dikkatli olmalı.",
            "Faulün bedeli sarı kart, {oyuncu} ({takim}).",
        ],
        second_yellow: [
            "İkinci sarıdan kırmızı! {oyuncu} oyun dışında, {dk}. dakika ({takim}).",
            "{oyuncu} ikinci sarıyı gördü ve oyundan atıldı! {takim} 10 kişi.",
            "Kırmızı kart! {oyuncu} ikinci sarıyla soyunma odasına gidiyor.",
            "{dk}. dakikada ikinci sarı: {oyuncu} oyuna veda ediyor ({takim}).",
            "Hakem ikinci sarıyı gösterdi, ardından kırmızı! {oyuncu} oyun dışı.",
        ],
        red: [
            "Direkt kırmızı kart! {oyuncu} oyun dışında, {dk}. dakika ({takim}).",
            "Hakem kırmızıyı çıkardı! {oyuncu} oyundan atıldı, {takim} 10 kişi.",
            "{dk}. dakikada kırmızı kart: {oyuncu} ({takim}).",
            "Maçın kırılma anı: {oyuncu} doğrudan kırmızı kart gördü.",
            "Kırmızı kart! {takim} tarafında {oyuncu} oyuna devam edemeyecek.",
        ],
        sub: [
            "{takim} değişikliği: giren {giren}, çıkan {cikan}. {dk}. dakika.",
            "Oyuna {giren} giriyor, {cikan} kenara geliyor ({takim}).",
            "{dk}. dakikada değişiklik: {cikan} yerine {giren} ({takim}).",
            "Taze kan: {giren} oyunda, {cikan} dinlenmeye çekiliyor.",
            "Teknik ekip hamlesini yaptı: {giren} girdi, {cikan} çıktı.",
            "{takim} tarafında oyuncu değişikliği: {cikan} çıktı, {giren} girdi.",
            "{cikan} alkışlarla kenara geliyor, yerine {giren}.",
            "Hücum hattına yeni bir isim: {giren}. Çıkan {cikan} ({takim}).",
            "{dk}. dakika, {takim} değişikliği: {giren} oyunda.",
            "Kenardan hareket var: {giren} giriyor, {cikan} çıkıyor.",
        ],
        var_goal_awarded: [
            "VAR incelemesi tamamlandı: gol geçerli! {dk}. dakika.",
            "Monitörden onay geldi, gol verildi.",
            "Hakem VAR sonrası golü onayladı.",
        ],
        var_goal_cancelled: [
            "VAR devrede ve gol iptal! {dk}. dakika.",
            "Monitöre giden hakem golü iptal etti.",
            "Sevinç yarım kaldı: VAR sonrası gol geçersiz.",
        ],
        var_penalty_awarded: [
            "VAR sonrası penaltı! {dk}. dakika.",
            "Hakem monitörü izledi ve beyaz noktayı gösterdi.",
            "VAR incelemesi penaltıyla sonuçlandı.",
        ],
        var_penalty_not_awarded: [
            "VAR incelemesi: penaltı yok, oyun devam ediyor.",
            "Monitörden penaltı çıkmadı, {dk}. dakika.",
            "Hakem kararını değiştirmedi: penaltı yok.",
        ],
        var_other: [
            "VAR incelemesi yapılıyor, {dk}. dakika.",
            "Hakem kulağını VAR'a verdi, karar bekleniyor.",
            "Pozisyon VAR'da inceleniyor.",
        ],
        penalty_missed: [
            "Penaltı kaçtı! {oyuncu} beyaz noktadan gole çeviremedi, {dk}. dakika.",
            "Kaleci kurtardı! {oyuncu} penaltıyı kaçırdı.",
            "{oyuncu} penaltıda başarısız, top ağlara gitmedi.",
            "Beyaz noktadan gol çıkmadı: {oyuncu} kaçırdı, {dk}. dakika.",
        ],
        penalty_other: [
            "Penaltı! {dk}. dakikada beyaz nokta, {takim} için.",
            "Hakem penaltı noktasını gösterdi, {dk}. dakika.",
        ],
        ht: [
            "İlk yarı sona erdi. {skor}",
            "Devre arası. Takımlar soyunma odasına gidiyor. {skor}",
            "Hakem ilk yarıyı bitirdi. {skor}",
            "İlk 45 dakika geride kaldı. {skor}",
        ],
        ft_win: [
            "Maç bitti, kazanan Fenerbahçe! {skor}",
            "Son düdük çaldı, üç puan Fenerbahçe hanesine! {skor}",
            "Tribünler bayram yapıyor, Fenerbahçe kazandı. {skor}",
            "Maç sona erdi, sarı-lacivertliler sahadan galip ayrılıyor. {skor}",
        ],
        ft_draw: [
            "Maç bitti, puanlar paylaşıldı. {skor}",
            "Son düdük çaldı, eşitlik bozulmadı. {skor}",
            "Karşılaşma beraberlikle sona erdi. {skor}",
        ],
        ft_loss: [
            "Maç bitti, Fenerbahçe sahadan mağlup ayrılıyor. {skor}",
            "Son düdük çaldı, bu maçtan puan çıkmadı. {skor}",
            "Acı bir akşam: Fenerbahçe kaybetti. {skor}",
        ],
    };

    // Basit ve kararlı karma: aynı metin her zaman aynı sayıyı verir
    function hash(s) {
        let h = 2166136261;
        for (let k = 0; k < s.length; k++) {
            h ^= s.charCodeAt(k);
            h = Math.imul(h, 16777619);
        }
        return h >>> 0;
    }

    function pick(group, key) {
        const list = T[group];
        return list[hash(key + "|" + group) % list.length];
    }

    function fill(text, v) {
        return text.replace(/\{(\w+)\}/g, (m, k) => (v[k] === undefined || v[k] === null || v[k] === "" ? "" : String(v[k])))
            .replace(/\s+([.,!?)])/g, "$1").replace(/\(\s*\)/g, "").replace(/\s{2,}/g, " ").trim();
    }

    function minute(i) {
        return (i.addedTime && i.addedTime < 100) ? `${i.time}+${i.addedTime}` : `${i.time ?? ""}`;
    }

    /* i: olay (/api/matches/{id}/detail biçimi), ctx: { home, away, fbIsHome,
       secondYellow (bu kart ikinci sarı mı) }. Döner: cümle ya da null. */
    function line(i, ctx) {
        if (!i || !ctx) return null;
        const fbIsHome = !!ctx.fbIsHome;
        const fbSide = i.isHome === undefined || i.isHome === null ? null : i.isHome === fbIsHome;
        const rakip = fbIsHome ? ctx.away : ctx.home;
        const score = (i.homeScore !== undefined && i.homeScore !== null)
            ? `${ctx.home} ${i.homeScore}-${i.awayScore} ${ctx.away}` : "";
        const v = {
            oyuncu: i.player, asist: i.assist, dk: minute(i), skor: score, fb: "Fenerbahçe", rakip,
            giren: i.playerIn, cikan: i.playerOut, takim: fbSide === null ? "" : (fbSide ? "Fenerbahçe" : rakip),
        };
        const key = [i.incidentType, i.incidentClass, i.time, i.addedTime, i.isHome, i.player, i.playerIn].join("|");
        let group = null;
        switch (i.incidentType) {
            case "goal":
                if (i.incidentClass === "ownGoal") group = fbSide ? "own_goal_for_fb" : "own_goal_for_rival";   // isHome: golün yazıldığı takım
                else if (i.incidentClass === "penalty") group = fbSide ? "penalty_goal_fb" : "penalty_goal_rival";
                else group = fbSide ? "goal_fb" : "goal_rival";
                if (!i.player) v.oyuncu = fbSide ? "Fenerbahçe" : rakip;
                break;
            case "card":
                if (ctx.secondYellow || i.incidentClass === "yellowRed") group = "second_yellow";
                else group = i.incidentClass === "yellow" ? "yellow" : "red";
                break;
            case "substitution":
                if (!i.playerIn && !i.playerOut) return fill(`${v.takim} oyuncu değişikliği, ${v.dk}. dakika.`, v);
                group = "sub";
                break;
            case "varDecision":
                group = {
                    goalAwarded: "var_goal_awarded", goalNotAwarded: "var_goal_cancelled",
                    penaltyAwarded: "var_penalty_awarded", penaltyNotAwarded: "var_penalty_not_awarded",
                }[i.incidentClass] || "var_other";
                break;
            case "inGamePenalty":
                group = i.incidentClass === "missed" ? "penalty_missed" : "penalty_other";
                break;
            case "period":
                if (i.text === "HT") group = "ht";
                else if (i.text === "FT") {
                    const fb = fbIsHome ? i.homeScore : i.awayScore;
                    const op = fbIsHome ? i.awayScore : i.homeScore;
                    group = fb > op ? "ft_win" : fb < op ? "ft_loss" : "ft_draw";
                }
                break;
        }
        if (!group) return null;
        let text = fill(pick(group, key), v);
        if (i.incidentType === "goal" && i.assist && i.incidentClass !== "ownGoal") {
            if (!/[.!?]$/.test(text)) text += ".";
            text += " " + fill(pick("assist", key), v);
        }
        return text;
    }

    const api = { line, templates: T, hash };
    root.Commentary = api;
    if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
