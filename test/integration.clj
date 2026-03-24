#!/usr/bin/env bb
;;
;; Integration test: installs evaleval from PyPI into an isolated venv,
;; then runs a smoke test against the installed package (not src/).
;;
;; Usage:
;;   bb test/integration.clj              # tests latest PyPI release
;;   bb test/integration.clj 0.2.6        # tests a specific version
;;
;; This is the post-release sanity check. It catches packaging mistakes
;; (missing files in wheel, wrong __all__, etc.) that unit tests miss
;; because unit tests run against src/ with PYTHONPATH set.

(require '[babashka.fs :as fs]
         '[babashka.process :as p]
         '[clojure.string :as str])

(def version (first *command-line-args*))
(def package (if version (str "evaleval==" version) "evaleval"))

(def tmpdir (str (fs/create-temp-dir)))
(def venv (str tmpdir "/venv"))
(def python (str venv "/bin/python"))
(def pip (str venv "/bin/pip"))

(println (str "Installing " package " into isolated venv..."))

(-> (p/process ["python3" "-m" "venv" venv] {:inherit true}) deref)
(-> (p/process [pip "install" "--quiet" package] {:inherit true}) deref)

(def installed-version
  (-> (p/process [python "-c" "import evaleval; print(evaleval.__version__ if hasattr(evaleval, '__version__') else 'unknown')"]
                 {:out :string})
      deref
      :out
      str/trim))

(println (str "Installed: " installed-version))

(def smoke-test "
import asyncio, json, pathlib, tempfile, sys

from evaleval import event, JsonlStore, to_dict, from_dict

@event
class Payment:
    amount: str
    wallet: str

@event
class Refund:
    amount: str

async def main():
    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d) / 'ledger.jsonl'
        store = JsonlStore(path)

        # empty on init
        assert store.read() == [], 'expected empty store'

        # append + read
        await store.append(Payment(amount='1.0', wallet='abc'))
        events = store.read()
        assert len(events) == 1
        assert isinstance(events[0], Payment)
        assert events[0].amount == '1.0'

        # to_dict / from_dict round-trip
        d2 = to_dict(events[0])
        assert d2['type'] == 'payment'
        assert from_dict(d2) == events[0]

        # atomic: guard against double-write
        def once(events):
            if any(isinstance(e, Refund) for e in events):
                return None
            return Refund(amount='0.5')

        r1 = await store.atomic(once)
        r2 = await store.atomic(once)
        assert r1 == Refund(amount='0.5'), f'expected Refund, got {r1}'
        assert r2 is None, f'expected None on second call, got {r2}'
        assert len(store.read()) == 2

        # replay: new store instance sees what was written
        store2 = JsonlStore(path)
        assert store2.read() == store.read(), 'replay mismatch'

        print('ok')

asyncio.run(main())
")

(println "Running smoke test...")
(let [result @(p/process [python "-c" smoke-test] {:inherit true})]
  (if (zero? (:exit result))
    (do (println (str "evaleval " installed-version " ok."))
        (fs/delete-tree tmpdir))
    (do (println "FAILED")
        (fs/delete-tree tmpdir)
        (System/exit 1))))
