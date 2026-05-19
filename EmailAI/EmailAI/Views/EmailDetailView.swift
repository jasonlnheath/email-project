import SwiftUI

struct EmailDetailView: View {
    let email: EmailItem
    @State private var isSummarizing = false
    @State private var summary: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Header
                VStack(alignment: .leading, spacing: 4) {
                    Text(email.subject)
                        .font(.title2)
                        .fontWeight(.bold)
                    HStack {
                        Text(email.sender)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(email.date, style: .date)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Divider()

                // Summary (if available)
                if let summary {
                    VStack(alignment: .leading, spacing: 4) {
                        Label("AI Summary", systemImage: "sparkles")
                            .font(.headline)
                        Text(summary)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding()
                    .background(Color(.systemGray6))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }

                // Body
                VStack(alignment: .leading, spacing: 4) {
                    Label("Full Email", systemImage: "doc.text")
                        .font(.headline)
                    Text(email.body)
                        .font(.body)
                        .textSelection(.enabled)
                }

                // Gmail link
                if !email.gmailUrl.isEmpty {
                    Link(destination: URL(string: email.gmailUrl)!) {
                        Label("Open in Gmail", systemImage: "arrow.up.right.square")
                    }
                    .font(.subheadline)
                }
            }
            .padding()
        }
        .navigationTitle("Email")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button(action: summarizeEmail) {
                    if isSummarizing {
                        ProgressView()
                    } else {
                        Label("Summarize", systemImage: "sparkles")
                    }
                }
                .disabled(isSummarizing)
            }
        }
    }

    private func summarizeEmail() {
        isSummarizing = true
        Task {
            do {
                let service = LLMProviderFactory.shared.getSelectedProvider()
                let result = try await service.summarizeEmail(
                    subject: email.subject,
                    sender: email.sender,
                    body: email.body
                )
                summary = result.summaryPurpose
            } catch {
                summary = "Error: \(error.localizedDescription)"
            }
            isSummarizing = false
        }
    }
}

struct EmailDetailView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            EmailDetailView(email: EmailItem(
                emailId: "test",
                subject: "Test Subject",
                sender: "test@example.com",
                date: Date(),
                body: "This is a test email body.",
                gmailUrl: "https://mail.google.com"
            ))
        }
    }
}
