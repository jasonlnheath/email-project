import Foundation
import Accelerate

/// In-memory vector index using cosine similarity — no external dependencies.
final class VectorIndex {
    private(set) var ids: [String] = []
    private(set) var vectors: [[Float]] = []
    let dim: Int

    init(dim: Int = Constants.embeddingDim) {
        self.dim = dim
    }

    var count: Int { ids.count }

    /// Add document vectors to the index.
    func add(ids: [String], vectors: [[Float]]) {
        precondition(ids.count == vectors.count)
        let normalized = vectors.map { normalize($0) }
        self.ids.append(contentsOf: ids)
        self.vectors.append(contentsOf: normalized)
    }

    /// Search for top-k most similar documents.
    func search(query: [Float], topK: Int = 5) -> [(id: String, score: Float)] {
        guard count > 0 else { return [] }

        let queryNorm = normalize(query)
        var results: [(id: String, score: Float)] = []

        for (i, docVec) in vectors.enumerated() {
            let score = cosineSimilarity(queryNorm, docVec)
            results.append((ids[i], score))
        }

        results.sort { $0.score > $1.score }
        return Array(results.prefix(topK))
    }

    // MARK: - Private

    private func normalize(_ vec: [Float]) -> [Float] {
        var sq: Float = 0
        vDSP_dotpr(vec, 1, vec, 1, &sq, vDSP_Length(vec.count))
        let norm = sqrt(sq)
        guard norm > 0 else { return vec }
        var result = [Float](repeating: 0, count: vec.count)
        var scale: Float = 1.0 / norm
        vDSP_vsmul(vec, 1, &scale, &result, 1, vDSP_Length(vec.count))
        return result
    }

    private func cosineSimilarity(_ a: [Float], _ b: [Float]) -> Float {
        precondition(a.count == b.count)
        var dot: Float = 0
        vDSP_dotpr(a, 1, b, 1, &dot, vDSP_Length(a.count))
        return dot  // Already normalized, so dot product = cosine similarity
    }
}
