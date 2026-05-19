import Foundation
import Combine

/// Search scope for email search
enum SearchScope: String, CaseIterable {
    case all = "All"
    case subject = "Subject"
    case sender = "Sender"
    case entities = "Entities"
    case summaries = "Summaries"

    var displayName: String {
        rawValue
    }
}

/// Email search result with relevance score
struct EmailSearchResult: Identifiable {
    let id: UUID
    let email: EmailItem
    let relevanceScore: Double
    let matchedFields: [String]
    let highlightedSnippet: String?
    let matchedEntities: [ExtractedEntity]

    init(
        id: UUID = UUID(),
        email: EmailItem,
        relevanceScore: Double,
        matchedFields: [String] = [],
        highlightedSnippet: String? = nil,
        matchedEntities: [ExtractedEntity] = []
    ) {
        self.id = id
        self.email = email
        self.relevanceScore = relevanceScore
        self.matchedFields = matchedFields
        self.highlightedSnippet = highlightedSnippet
        self.matchedEntities = matchedEntities
    }
}

/// Advanced email search service
actor EmailSearchService {
    private var indexedEmails: [EmailItem] = []
    private var entityIndex: [String: [ExtractedEntity]] = [:] // emailId -> entities
    private var emailIdMap: [String: EmailItem] = [:] // emailId -> email

    // Search components
    private var bm25: BM25?
    private let vectorIndex = VectorIndex()

    /// Number of indexed emails
    var indexedEmailsCount: Int {
        indexedEmails.count
    }

    // MARK: - Indexing

    /// Index emails for search
    func indexEmails(_ emails: [EmailItem]) async {
        self.indexedEmails = emails
        self.emailIdMap = Dictionary(uniqueKeysWithValues: emails.map { ($0.emailId, $0) })

        // Build entity index
        var newEntityIndex: [String: [ExtractedEntity]] = [:]

        for email in emails {
            let entities = EntityExtractor.extract(from: email.body)
            newEntityIndex[email.emailId] = entities
        }

        self.entityIndex = newEntityIndex

        // Build BM25 index from email text
        let bm25Index = BM25()
        let documents = emails.map { "\($0.subject) \($0.sender) \($0.body)" }
        bm25Index.fit(documents: documents)
        self.bm25 = bm25Index

        // Note: Vector index would require embeddings, which we're skipping for now
        // In production, you'd generate embeddings using EmbeddingService
    }

    // MARK: - Search

    /// Search emails with specified scope
    func search(
        query: String,
        scope: SearchScope = .all,
        limit: Int = 50
    ) async throws -> [EmailSearchResult] {

        let trimmedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedQuery.isEmpty else {
            return []
        }

        var results: [EmailSearchResult] = []

        switch scope {
        case .all:
            // Combined BM25 + vector search
            let textResults = try await bm25Search(trimmedQuery, limit: limit)
            let semanticResults = try await vectorSearch(trimmedQuery, limit: limit)
            let entityResults = try await entitySearch(trimmedQuery, limit: limit)

            // Merge and re-rank results
            results = mergeResults(
                textResults,
                semanticResults,
                entityResults
            )

        case .subject:
            results = try await fieldSearch(trimmedQuery, fields: ["subject"], limit: limit)

        case .sender:
            results = try await fieldSearch(trimmedQuery, fields: ["sender"], limit: limit)

        case .entities:
            results = try await entitySearch(trimmedQuery, limit: limit)

        case .summaries:
            // Search in summaries only
            results = try await summarySearch(trimmedQuery, limit: limit)
        }

        // Sort by relevance and limit
        return results
            .sorted { $0.relevanceScore > $1.relevanceScore }
            .prefix(limit)
            .map { $0 }
    }

    // MARK: - Search Methods

    private func bm25Search(_ query: String, limit: Int) async throws -> [EmailSearchResult] {
        guard let bm25 = bm25 else {
            return []
        }

        let results = bm25.score(query: query, topK: limit)

        return results.compactMap { result in
            guard result.index < indexedEmails.count else {
                return nil
            }
            let email = indexedEmails[result.index]

            return EmailSearchResult(
                email: email,
                relevanceScore: Double(result.score),
                matchedFields: ["body"],
                highlightedSnippet: highlightSnippet(in: email.body, query: query)
            )
        }
    }

    private func vectorSearch(_ query: String, limit: Int) async throws -> [EmailSearchResult] {
        // Vector search would require embeddings, which we're skipping for now
        // In production, you'd use EmbeddingService to generate query embedding
        return []
    }

    private func entitySearch(_ query: String, limit: Int) async throws -> [EmailSearchResult] {
        var results: [EmailSearchResult] = []

        for (emailId, entities) in entityIndex {
            let matchingEntities = entities.filter { entity in
                entity.value.localizedCaseInsensitiveContains(query)
            }

            if !matchingEntities.isEmpty {
                if let email = emailIdMap[emailId] {
                    results.append(EmailSearchResult(
                        email: email,
                        relevanceScore: 0.9, // High weight for entity matches
                        matchedFields: ["entities"],
                        matchedEntities: matchingEntities
                    ))
                }
            }
        }

        return results
    }

    private func fieldSearch(_ query: String, fields: [String], limit: Int) async throws -> [EmailSearchResult] {
        var results: [EmailSearchResult] = []
        let lowercaseQuery = query.lowercased()

        for email in indexedEmails {
            var matchedFields: [String] = []
            var relevanceScore: Double = 0.0

            for field in fields {
                let fieldValue: String
                switch field {
                case "subject":
                    fieldValue = email.subject
                case "sender":
                    fieldValue = email.sender
                default:
                    continue
                }

                if fieldValue.localizedCaseInsensitiveContains(query) {
                    matchedFields.append(field)
                    relevanceScore += 0.8
                }
            }

            if !matchedFields.isEmpty {
                results.append(EmailSearchResult(
                    email: email,
                    relevanceScore: relevanceScore,
                    matchedFields: matchedFields,
                    highlightedSnippet: nil
                ))
            }
        }

        return results
    }

    private func summarySearch(_ query: String, limit: Int) async throws -> [EmailSearchResult] {
        var results: [EmailSearchResult] = []
        let lowercaseQuery = query.lowercased()

        for email in indexedEmails {
            if let summary = email.summary,
               summary.localizedCaseInsensitiveContains(query) {

                results.append(EmailSearchResult(
                    email: email,
                    relevanceScore: 0.85,
                    matchedFields: ["summary"],
                    highlightedSnippet: highlightSnippet(in: summary, query: query)
                ))
            }
        }

        return results
    }

    // MARK: - Result Merging

    private func mergeResults(
        _ textResults: [EmailSearchResult],
        _ semanticResults: [EmailSearchResult],
        _ entityResults: [EmailSearchResult]
    ) -> [EmailSearchResult] {
        var merged: [String: EmailSearchResult] = [:]

        // Combine scores for emails that appear in multiple result sets
        for result in textResults + semanticResults + entityResults {
            let emailId = result.email.emailId

            if let existing = merged[emailId] {
                // Combine relevance scores with weights
                let combinedScore = existing.relevanceScore * 0.5 + result.relevanceScore * 0.5

                // Merge matched fields
                var mergedFields = existing.matchedFields
                for field in result.matchedFields {
                    if !mergedFields.contains(field) {
                        mergedFields.append(field)
                    }
                }

                // Merge entities
                var mergedEntities = existing.matchedEntities
                mergedEntities.append(contentsOf: result.matchedEntities)

                merged[emailId] = EmailSearchResult(
                    email: result.email,
                    relevanceScore: combinedScore,
                    matchedFields: mergedFields,
                    highlightedSnippet: result.highlightedSnippet ?? existing.highlightedSnippet,
                    matchedEntities: mergedEntities
                )
            } else {
                merged[emailId] = result
            }
        }

        return Array(merged.values)
    }

    // MARK: - Snippet Highlighting

    private func highlightSnippet(in text: String, query: String) -> String {
        let terms = query.components(separatedBy: .whitespaces).filter { !$0.isEmpty }

        // Find the best snippet containing the query terms
        let snippetLength = 150
        let lowercaseText = text.lowercased()

        for term in terms {
            if let range = lowercaseText.range(of: term.lowercased()) {
                // Extend range to get context
                let start = max(text.startIndex, text.index(range.lowerBound, offsetBy: -snippetLength/2))
                let end = min(text.endIndex, text.index(range.upperBound, offsetBy: snippetLength/2))

                let snippet = String(text[start..<end])
                return "...\(snippet.trimmingCharacters(in: .whitespaces))..."
            }
        }

        // Fallback: return first snippetLength characters
        if text.count > snippetLength {
            let index = text.index(text.startIndex, offsetBy: snippetLength)
            return String(text[..<index]) + "..."
        }

        return text
    }

    // MARK: - Entity Search

    /// Get entities for a specific email
    func getEntities(for emailId: String) -> [ExtractedEntity] {
        return entityIndex[emailId] ?? []
    }

    /// Search all entities across all emails
    func searchAllEntities(_ query: String) -> [(emailId: String, entities: [ExtractedEntity])] {
        var results: [(String, [ExtractedEntity])] = []

        for (emailId, entities) in entityIndex {
            let matchingEntities = entities.filter { entity in
                entity.value.localizedCaseInsensitiveContains(query)
            }

            if !matchingEntities.isEmpty {
                results.append((emailId, matchingEntities))
            }
        }

        return results
    }
}
