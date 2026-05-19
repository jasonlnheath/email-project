import Foundation

/// Embedding service — calls cloud API to generate text embeddings.
actor EmbeddingService {
    private let baseURL: String
    private let model: String
    let dim: Int

    init(baseURL: String = Constants.anthropicBaseURL, model: String = Constants.anthropicModelDefault, dim: Int = Constants.embeddingDim) {
        self.baseURL = baseURL
        self.model = model
        self.dim = dim
    }

    /// Get embedding for a single text.
    func embed(_ text: String) async -> [Float] {
        let results = await embedBatch([text])
        return results.first ?? Array(repeating: 0, count: dim)
    }

    /// Get embeddings for multiple texts in one API call.
    func embedBatch(_ texts: [String]) async -> [[Float]] {
        if texts.isEmpty { return [] }

        guard let apiKey = KeychainService.shared.load(key: Constants.keychainAnthropicKey) else {
            return texts.map { _ in Array(repeating: Float(0), count: dim) }
        }

        do {
            let url = URL(string: "\(baseURL)/v1/embeddings")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")

            let body: [String: Any] = [
                "model": model,
                "input": texts,
            ]
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.timeoutInterval = 30

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                return texts.map { _ in Array(repeating: Float(0), count: dim) }
            }

            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let embeddingData = json?["data"] as? [[String: Any]] ?? []
            return embeddingData.compactMap { item in
                (item["embedding"] as? [Double])?.map { Float($0) }
            }
        } catch {
            return texts.map { _ in Array(repeating: Float(0), count: dim) }
        }
    }
}
