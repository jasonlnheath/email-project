import Foundation

/// Anthropic Claude API provider
actor AnthropicProvider: LLMProvider {
    private let baseURL: String
    private let model: String

    init(baseURL: String = Constants.anthropicBaseURL, model: String = Constants.anthropicModelDefault) {
        self.baseURL = baseURL
        self.model = model
    }

    /// Send a chat completion request and return the response text
    func chat(messages: [[String: String]], systemPrompt: String? = nil) async throws -> String {
        guard let apiKey = KeychainService.shared.load(key: Constants.keychainAnthropicKey) else {
            throw LLMError.missingAPIKey
        }

        guard let url = URL(string: "\(baseURL)/v1/messages") else {
            throw LLMError.apiError(statusCode: 0, body: "Invalid URL: \(baseURL)")
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")

        var body: [String: Any] = [
            "model": model,
            "max_tokens": 2048,
            "messages": messages,
        ]
        if let systemPrompt {
            body["system"] = systemPrompt
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        request.timeoutInterval = 60

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
            let responseBody = String(data: data, encoding: .utf8) ?? ""
            throw LLMError.apiError(statusCode: statusCode, body: responseBody)
        }

        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let content = json?["content"] as? [[String: Any]] ?? []
        let text = content.compactMap { $0["text"] as? String }.joined()

        return text
    }

    /// Summarize a single email
    func summarizeEmail(subject: String, sender: String, body: String) async throws -> SummarizeResult {
        print("\n🤖 === Anthropic summarizeEmail() called ===")
        print("📧 Input body length: \(body.count)")
        print("📧 Input body preview: \(String(body.prefix(200)))")

        if body.isEmpty {
            print("⚠️⚠️⚠️ BODY IS EMPTY! ⚠️⚠️⚠️")
        }

        let truncated = truncateBody(body, maxLength: 3000)
        print("📧 Truncated body length: \(truncated.count)")

        // Pre-extract concrete entities as anchors
        let anchors = extractEntities(from: truncated)
        var anchorText = ""
        if !anchors.money.isEmpty {
            anchorText += "Money found: \(anchors.money.joined(separator: ", "))\n"
        }
        if !anchors.phones.isEmpty {
            anchorText += "Phone numbers found: \(anchors.phones.joined(separator: ", "))\n"
        }
        if !anchors.urls.isEmpty {
            anchorText += "URLs found: \(anchors.urls.prefix(5).joined(separator: ", "))\n"
        }
        if !anchors.dates.isEmpty {
            anchorText += "Dates found: \(anchors.dates.joined(separator: ", "))\n"
        }
        if !anchors.emails.isEmpty {
            anchorText += "Email addresses found: \(anchors.emails.prefix(3).joined(separator: ", "))\n"
        }

        let messages: [[String: String]] = [
            ["role": "user", "content": """
            Analyze this email and extract structured information.

            FROM: \(sender)
            SUBJECT: \(subject)
            DATE: \(Date())

            BODY:
            \(truncated)

            \(anchorText)

            Extract the following and return ONLY valid JSON (no markdown, no extra text):
            - summary_purpose: A detailed 2-3 sentence summary explaining what this email is about, including specific facts, details, and context. NOT just the subject line.
            - key_entities: list of 3-8 concrete entities EXTRACTED FROM THE EMAIL BODY. Include: person names, company names, product names, specific dates, dollar amounts, account numbers, file names, URLs. DO NOT invent or infer entities not explicitly stated.
            - action_items: list of 0-5 specific actions requested or required. An action item is a REQUEST, DEADLINE, or TASK directed at someone. Examples: 'Reply by Friday', 'Review attached PDF', 'Call Sarah at (555) 123-4567'. Do NOT include general statements like 'Please review' without specifics.
            - sentiment: one of 'positive', 'negative', 'neutral'

            CRITICAL RULES:
            1. ONLY extract what appears in the email body. Do NOT guess or infer.
            2. If an entity/action is not explicitly stated, omit it — do NOT fabricate.
            3. Dollar amounts must include the $ sign and exact figure from the email.
            4. Phone numbers must match exactly as written in the email.
            5. Dates must match exactly (e.g., 'March 15' not 'mid-March').
            6. The summary_purpose should include FACTS and DETAILS from the email body, not just restate the subject.
            7. Return JSON only, no other text.

            Expected format:
            {
              "summary_purpose": "detailed 2-3 sentence summary with facts and details from the email body",
              "key_entities": ["entity1", "entity2", "entity3"],
              "action_items": ["specific action 1", "specific action 2"],
              "sentiment": "neutral"
            }
            """],
        ]

        print("📤 Sending prompt to Anthropic, length: \(messages[0]["content"]?.count ?? 0)")
        print("📤 Prompt preview (first 500 chars): \(String((messages[0]["content"] ?? "").prefix(500)))")

        let response = try await chat(messages: messages)

        print("📥 Anthropic response length: \(response.count)")
        print("📥 Anthropic response preview: \(String(response.prefix(500)))")

        let result = parseSummaryResponse(response, body: truncated)

        print("✅ Parsed summary_purpose: \(result.summaryPurpose.prefix(100))...")
        print("✅ Parsed key_entities: \(result.keyEntities)")
        print("✅ Parsed action_items: \(result.actionItems)")

        return result
    }

    private func parseSummaryResponse(_ text: String, body: String) -> SummarizeResult {
        // Extract JSON from response - support nested braces
        guard let range = text.range(of: "\\{[\\s\\S]*?\\}", options: .regularExpression) else {
            return SummarizeResult(summaryPurpose: text, keyEntities: [], actionItems: [], sentiment: "neutral")
        }
        let jsonStr = String(text[range])
        guard let data = jsonStr.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return SummarizeResult(summaryPurpose: text, keyEntities: [], actionItems: [], sentiment: "neutral")
        }

        let keyEntities = json["key_entities"] as? [String] ?? []
        let actionItems = json["action_items"] as? [String] ?? []

        // Verify entities and actions against original body to catch hallucinations
        let verifiedEntities = verifyEntities(keyEntities, against: body)
        let verifiedActions = verifyEntities(actionItems, against: body)

        return SummarizeResult(
            summaryPurpose: json["summary_purpose"] as? String ?? "",
            keyEntities: verifiedEntities,
            actionItems: verifiedActions,
            sentiment: json["sentiment"] as? String ?? "neutral"
        )
    }

    /// Verify that extracted entities/actions actually appear in the original body
    private func verifyEntities(_ items: [String], against body: String) -> [String] {
        let bodyLower = body.lowercased()
        return items.filter { item in
            let itemLower = item.lowercased()
            return itemLower.count > 2 && bodyLower.contains(itemLower)
        }
    }

    /// Extract concrete entities using regex as anchors for the LLM
    private func extractEntities(from text: String) -> (money: [String], phones: [String], urls: [String], dates: [String], emails: [String]) {
        var money: [String] = []
        var phones: [String] = []
        var urls: [String] = []
        var dates: [String] = []
        var emails: [String] = []

        // Money: $5,000 or $5.2k
        if let moneyRegex = try? NSRegularExpression(pattern: #"\\$[\d,]+(?:\.\d{2})?"#) {
            money = matches(for: moneyRegex, in: text)
        }

        // Phone numbers: (555) 123-4567, 555-123-4567, 555.123.4567
        if let phoneRegex = try? NSRegularExpression(pattern: #"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"#) {
            phones = matches(for: phoneRegex, in: text)
        }

        // URLs
        if let urlRegex = try? NSRegularExpression(pattern: #"https?://[^\s<>"]+|www\.[^\s<>"]+"#) {
            urls = matches(for: urlRegex, in: text)
        }

        // Dates: Month DD, YYYY
        if let dateRegex = try? NSRegularExpression(pattern: #"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}"#, options: .caseInsensitive) {
            dates = matches(for: dateRegex, in: text)
        }

        // Email addresses
        if let emailRegex = try? NSRegularExpression(pattern: #"[\w\.-]+@[\w\.-]+\.\w+"#) {
            emails = matches(for: emailRegex, in: text)
        }

        return (Array(Set(money)), Array(Set(phones)), Array(Set(urls)), Array(Set(dates)), Array(Set(emails)))
    }

    private func matches(for regex: NSRegularExpression, in text: String) -> [String] {
        let range = NSRange(text.startIndex..., in: text)
        let matches = regex.matches(in: text, range: range)
        return matches.compactMap {
            guard let range = Range($0.range, in: text) else { return nil }
            return String(text[range])
        }
    }

    /// Truncate body symmetrically (keep beginning + end, like Hermes)
    private func truncateBody(_ body: String, maxLength: Int = 3000) -> String {
        if body.count <= maxLength {
            return body
        }

        let marker = "\n\n... [email truncated] ...\n\n"
        let available = maxLength - marker.count
        let half = available / 2

        return String(body.prefix(half)) + marker + String(body.suffix(half))
    }
}
