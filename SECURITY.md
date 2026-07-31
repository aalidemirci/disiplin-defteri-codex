# Güvenlik ve kişisel veri bildirimi

Disiplin Defteri hassas eğitim verileriyle çalışır. Güvenlik bildirimi yaparken
öğrenci, veli, personel veya kurumlara ait gerçek verileri herkese açık issue,
discussion, ekran görüntüsü, günlük ya da örnek dosyalara eklemeyin.

## Güvenlik açığı bildirme

Güvenlik bildirimlerini herkese açık kayıt açmadan önce
`aalidemirci@gmail.com` adresine iletin. Bildirimde mümkünse yalnızca:

- etkilenen sürüm ve işletim sistemi,
- kişisel veri içermeyen yeniden üretme adımları,
- beklenen ve gerçekleşen davranış,
- anonimleştirilmiş teknik günlük

bulunsun. Gerçek veritabanı, yedek, öğrenci listesi veya kurum belgesi
göndermeyin.

## Desteklenen sürüm

Güvenlik düzeltmeleri en güncel GitHub sürümüne uygulanır. Beta sürümler test
amaçlıdır; üretim verileriyle kullanılmadan önce şifreli yedek alınmalıdır.

## Bilinen bağımlılık bildirimi

Tarayıcı arayüzü yalnızca istemci taraflı bir SPA olarak çalışır; React Server
Components ve sunucu eylemleri kullanılmaz. React Router'ın bu kullanılmayan
sunucu kipini etkileyen `GHSA-qwww-vcr4-c8h2` bildirimi için yayımlanmış güvenli
bir 7.x sürümü bulunmadığından paket güncel 7.x sürümünde tutulmaktadır. Proje bu
özelliği etkinleştirirse bildirim yeniden değerlendirilecektir.
