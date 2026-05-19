import Foundation

/// Combines BM25 (keyword) and semantic (embedding) scores.
struct HybridScorer {
    let bm25Weight: Float
    let semanticWeight: Float

    init(bm25Weight: Float = 0.4, semanticWeight: Float = 0.6) {
        let total = bm25Weight + semanticWeight
        self.bm25Weight = bm25Weight / total
        self.semanticWeight = semanticWeight / total
    }

    /// Combine scores from BM25 and semantic search.
    func combine(bm25Scores: [String: Float], semanticScores: [String: Float]) -> [String: Float] {
        guard !bm25Scores.isEmpty || !semanticScores.isEmpty else { return [:] }

        let normBM25 = normalize(bm25Scores)
        let normSemantic = normalize(semanticScores)

        let allIds = Set(bm25Scores.keys).union(semanticScores.keys)

        var combined: [String: Float] = [:]
        for id in allIds {
            let b = normBM25[id] ?? 0
            let s = normSemantic[id] ?? 0
            combined[id] = bm25Weight * b + semanticWeight * s
        }
        return combined
    }

    private func normalize(_ scores: [String: Float]) -> [String: Float] {
        guard !scores.isEmpty else { return [:] }
        let values = Array(scores.values)
        let minVal = values.min() ?? 0
        let maxVal = values.max() ?? 0
        guard maxVal > minVal else { return scores.mapValues { _ in 0 } }
        return scores.mapValues { ($0 - minVal) / (maxVal - minVal) }
    }
}
