import Foundation

/// Unified search service combining BM25 + semantic search.
class SearchService: ObservableObject {
    private let bm25 = BM25()
    private let vectorIndex: VectorIndex
    private let hybridScorer = HybridScorer()
    private let embeddingService: EmbeddingService

    @Published var isIndexed = false

    init(dim: Int = Constants.embeddingDim) {
        self.vectorIndex = VectorIndex(dim: dim)
        self.embeddingService = EmbeddingService(dim: dim)
    }

    /// Build search index from stored emails and summaries.
    func buildIndex(emails: [EmailItem], summaries: [SummaryItem]) async {
        let allTexts = emails.map { $0.body } + summaries.map { $0.summaryPurpose }
        bm25.fit(documents: allTexts)

        if !summaries.isEmpty {
            let texts = summaries.map { "\($0.summaryPurpose) \($0.keyEntities.joined())" }
            let vectors = await embeddingService.embedBatch(texts)
            let ids = summaries.map { $0.emailId }
            vectorIndex.add(ids: ids, vectors: vectors)
        }

        isIndexed = true
    }

    /// Search for emails matching a query using hybrid scoring.
    func search(query: String, topK: Int = 10) async -> [SearchResult] {
        guard isIndexed else { return [] }

        let bm25Results = bm25.score(query: query, topK: topK * 3)
        var bm25Scores: [String: Float] = [:]
        for (index, score) in bm25Results {
            bm25Scores["doc_\(index)"] = Float(score)
        }

        let queryVec = await embeddingService.embed(query)
        let semResults = vectorIndex.search(query: queryVec, topK: topK * 3)
        var semanticScores: [String: Float] = [:]
        for (id, score) in semResults {
            semanticScores[id] = score
        }

        let combined = hybridScorer.combine(bm25Scores: bm25Scores, semanticScores: semanticScores)
        let ranked = combined.sorted { $0.value > $1.value }

        return ranked.prefix(topK).map { (id, score) in
            SearchResult(id: id, score: score)
        }
    }
}

struct SearchResult: Identifiable {
    let id: String
    let score: Float
}
