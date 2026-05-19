import Foundation

/// Summarization pipeline — processes emails into tier summaries.
class SummarizerService: ObservableObject {

    /// Get the current LLM provider from factory
    private func getLLM() -> LLMProvider {
        LLMProviderFactory.shared.getSelectedProvider()
    }

    /// Summarize a single email.
    func summarize(email: EmailItem) async throws -> SummaryItem {
        let llm = getLLM()
        let result = try await llm.summarizeEmail(
            subject: email.subject,
            sender: email.sender,
            body: email.body
        )

        return SummaryItem(
            emailId: email.emailId,
            subject: email.subject,
            sender: email.sender,
            date: email.date,
            summaryPurpose: result.summaryPurpose,
            keyEntities: result.keyEntities,
            actionItems: result.actionItems,
            sentiment: result.sentiment,
            gmailUrl: email.gmailUrl
        )
    }

    /// Batch summarize multiple emails.
    func summarizeBatch(emails: [EmailItem]) async throws -> [SummaryItem] {
        var summaries: [SummaryItem] = []
        for email in emails {
            do {
                let summary = try await summarize(email: email)
                summaries.append(summary)
            } catch {
                print("Failed to summarize \(email.emailId): \(error)")
            }
        }
        return summaries
    }
}
