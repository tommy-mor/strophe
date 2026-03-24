#!/usr/bin/env bb

(require '[babashka.fs :as fs]
         '[babashka.process :as p])

(def script-dir (str (fs/canonicalize (fs/parent *file*))))
(def local-src (str script-dir "/src"))
(def py-path (let [existing (System/getenv "PYTHONPATH")]
               (if (seq existing) (str local-src ":" existing) local-src)))

(println "=== unit tests ===")
(let [result @(p/process (into ["uv" "run" "pytest"] *command-line-args*)
                         {:inherit true :extra-env {"PYTHONPATH" py-path}})]
  (when-not (zero? (:exit result))
    (System/exit (:exit result))))

(println "\n=== integration test ===")
(let [result @(p/process ["bb" (str script-dir "/test/integration.clj")]
                         {:inherit true})]
  (System/exit (:exit result)))
