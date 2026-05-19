import Foundation

/// Simplified Okapi BM25 scorer — ported from Python retrieval.py.
final class BM25 {
    private var docs: [[String]] = []
    private var idf: [String: Double] = [:]
    private var avgdl: Double = 0
    private let k1: Double
    private let b: Double

    init(k1: Double = 1.5, b: Double = 0.75) {
        self.k1 = k1
        self.b = b
    }

    /// Index documents for searching.
    func fit(documents: [String]) {
        var totalTokens = 0
        var docFreq: [String: Int] = [:]
        docs = []

        for doc in documents {
            let tokens = tokenize(doc)
            docs.append(tokens)
            totalTokens += tokens.count
            for token in Set(tokens) {
                docFreq[token, default: 0] += 1
            }
        }

        let n = Double(docs.count)
        avgdl = Double(totalTokens) / max(n, 1.0)

        for (term, df) in docFreq {
            idf[term] = Foundation.log((n - Double(df) + 0.5) / (Double(df) + 0.5) + 1.0)
        }
    }

    /// Score documents against a query. Returns [(docIndex, score)] sorted by score descending.
    func score(query: String, topK: Int? = nil) -> [(index: Int, score: Double)] {
        let queryTokens = tokenize(query)
        var scores: [(index: Int, score: Double)] = []

        for (i, docTokens) in docs.enumerated() {
            var s = 0.0
            let dl = Double(docTokens.count)
            let termFreqs = Dictionary(grouping: docTokens, by: { $0 }).mapValues { $0.count }

            for term in Set(queryTokens) {
                let tf = Double(termFreqs[term] ?? 0)
                let idfVal = idf[term] ?? 0
                let numerator = tf * (k1 + 1)
                let denominator = tf + k1 * (1 - b + b * dl / avgdl)
                s += idfVal * numerator / denominator
            }
            scores.append((i, s))
        }

        scores.sort { $0.score > $1.score }
        if let topK { return Array(scores.prefix(topK)) }
        return scores
    }

    private func tokenize(_ text: String) -> [String] {
        text.lowercased().components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }
    }
}
