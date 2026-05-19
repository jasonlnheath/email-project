import Foundation
import NaturalLanguage

/// Extracted entity from email text
struct ExtractedEntity: Identifiable, Hashable {
    let id = UUID()
    let type: EntityType
    let value: String
    let range: Range<String.Index>
    let confidence: Double

    enum EntityType: String, CaseIterable {
        case email = "Email"
        case url = "URL"
        case phoneNumber = "Phone"
        case date = "Date"
        case money = "Money"
        case company = "Company"
        case project = "Project"
        case actionItem = "Action Item"
        case attachment = "Attachment"

        var icon: String {
            switch self {
            case .email: return "envelope"
            case .url: return "link"
            case .phoneNumber: return "phone"
            case .date: return "calendar"
            case .money: return "dollarsign.circle"
            case .company: return "building"
            case .project: return "folder"
            case .actionItem: return "checkmark.circle"
            case .attachment: return "paperclip"
            }
        }

        var color: String {
            switch self {
            case .email: return "blue"
            case .url: return "purple"
            case .phoneNumber: return "green"
            case .date: return "orange"
            case .money: return "red"
            case .company: return "indigo"
            case .project: return "teal"
            case .actionItem: return "yellow"
            case .attachment: return "gray"
            }
        }
    }
}

/// Entity extractor for email content
struct EntityExtractor {

    /// Extract all entities from email text
    static func extract(from text: String) -> [ExtractedEntity] {
        var entities: [ExtractedEntity] = []

        // Basic regex-based extraction
        entities.append(contentsOf: extractEmails(from: text))
        entities.append(contentsOf: extractURLs(from: text))
        entities.append(contentsOf: extractPhoneNumbers(from: text))
        entities.append(contentsOf: extractMoney(from: text))
        entities.append(contentsOf: extractDates(from: text))

        // Advanced NLP-based extraction
        entities.append(contentsOf: extractCompanies(from: text))
        entities.append(contentsOf: extractProjects(from: text))
        entities.append(contentsOf: extractActionItems(from: text))
        entities.append(contentsOf: extractAttachments(from: text))

        return entities
    }

    // MARK: - Regex-based Extraction

    private static func extractEmails(from text: String) -> [ExtractedEntity] {
        let pattern = #"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"#
        return extractWithPattern(pattern, type: .email, from: text)
    }

    private static func extractURLs(from text: String) -> [ExtractedEntity] {
        let pattern = #"https?://[^\s<>"{}|\\^`\[\]]+"#
        var urls = extractWithPattern(pattern, type: .url, from: text)

        // Also match Google Drive links
        let drivePattern = #"drive\.google\.com/[^\s<>"{}|\\^`\[\]]+"#
        urls.append(contentsOf: extractWithPattern(drivePattern, type: .url, from: text))

        return urls
    }

    private static func extractPhoneNumbers(from text: String) -> [ExtractedEntity] {
        // US phone numbers: (555) 123-4567, 555-123-4567, 555.123.4567
        let pattern = #"(\(\d{3}\)\s?|\d{3}[-.]?)?\d{3}[-.]?\d{4}"#
        return extractWithPattern(pattern, type: .phoneNumber, from: text)
    }

    private static func extractMoney(from text: String) -> [ExtractedEntity] {
        // $5,000, $5.2k, €100, £50, etc.
        let pattern = #"[$€£¥₹][\d,]+\.?\d*[kKmMbB]?"#
        return extractWithPattern(pattern, type: .money, from: text)
    }

    private static func extractDates(from text: String) -> [ExtractedEntity] {
        var dates: [ExtractedEntity] = []

        // Common date formats:
        // - March 15, 2025
        // - 03/15/2025, 03-15-2025
        // - "next Monday", "tomorrow", "in 2 weeks"
        let patterns = [
            #"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}"#,
            #"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"#,
            #"(?:next|this|last)\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"#,
            #"(?:today|tomorrow|yesterday)"#
        ]

        for pattern in patterns {
            dates.append(contentsOf: extractWithPattern(pattern, type: .date, from: text))
        }

        return dates
    }

    // MARK: - NLP-based Extraction

    private static func extractCompanies(from text: String) -> [ExtractedEntity] {
        var companies: [ExtractedEntity] = []

        // Use NLTagger to extract organization names
        let tagger = NLTagger(tagSchemes: [.nameType])
        tagger.string = text

        let options: NLTagger.Options = [.omitPunctuation, .omitWhitespace]
        let range = text.startIndex..<text.endIndex

        tagger.enumerateTags(in: range, unit: .word, scheme: .nameType, options: options) { tag, range in
            if tag == .organizationName {
                let company = String(text[range])
                companies.append(ExtractedEntity(
                    type: .company,
                    value: company,
                    range: range,
                    confidence: 0.8
                ))
            }
            return true
        }

        return companies
    }

    private static func extractProjects(from text: String) -> [ExtractedEntity] {
        var projects: [ExtractedEntity] = []

        // Look for project name patterns:
        // - "Project: X", "project X"
        // - "RE: X" (common in email subjects)
        // - "[X]" format
        let patterns = [
            #"(?i)project\s+[:\-]?\s*([A-Z][A-Za-z0-9\s]+)"#,
            #"(?i)RE\s*:\s*([A-Z][A-Za-z0-9\s]+)"#,
            #"\[([A-Z][A-Za-z0-9\s]+)\]"#
        ]

        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern) {
                let range = NSRange(text.startIndex..., in: text)
                let matches = regex.matches(in: text, range: range)

                for match in matches {
                    if let range = Range(match.range(at: 1), in: text) {
                        let project = String(text[range])
                        projects.append(ExtractedEntity(
                            type: .project,
                            value: project,
                            range: range,
                            confidence: 0.7
                        ))
                    }
                }
            }
        }

        return projects
    }

    private static func extractActionItems(from text: String) -> [ExtractedEntity] {
        var actionItems: [ExtractedEntity] = []

        // Look for action item patterns:
        // - "TODO: X", "ACTION: X"
        // - "Please X by date"
        // - "Need to X", "Follow up on X"
        let patterns = [
            #"(?i)(?:TODO|ACTION|TASK)\s*:\s*(.+?)(?:\.|$)"#,
            #"(?i)please\s+(.+?)(?:\s+by\s+|\.)"#,
            #"(?i)(?:need to|follow up on|should)\s+(.+?)(?:\.|$)"#
        ]

        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern) {
                let nsRange = NSRange(text.startIndex..., in: text)
                let matches = regex.matches(in: text, range: nsRange)

                for match in matches {
                    if let range = Range(match.range(at: 1), in: text) {
                        let action = String(text[range]).trimmingCharacters(in: .whitespaces)
                        if action.count > 5 { // Filter out very short matches
                            actionItems.append(ExtractedEntity(
                                type: .actionItem,
                                value: action,
                                range: range,
                                confidence: 0.6
                            ))
                        }
                    }
                }
            }
        }

        return actionItems
    }

    private static func extractAttachments(from text: String) -> [ExtractedEntity] {
        var attachments: [ExtractedEntity] = []

        // Look for attachment references:
        // - "attached: X", "see attached X"
        // - File extensions: .pdf, .doc, .xls, etc.
        let patterns = [
            #"(?i)attached\s*[:\-]?\s*(.+?)(?:\.|\n)"#,
            #"(?i)see\s+attached\s+(.+?)(?:\.|\n)"#,
            #"\S+\.(pdf|doc|docx|xls|xlsx|ppt|pptx|zip|png|jpg|jpeg)"#
        ]

        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern) {
                let nsRange = NSRange(text.startIndex..., in: text)
                let matches = regex.matches(in: text, range: nsRange)

                for match in matches {
                    if let range = Range(match.range(at: 0), in: text) {
                        let attachment = String(text[range])
                        attachments.append(ExtractedEntity(
                            type: .attachment,
                            value: attachment,
                            range: range,
                            confidence: 0.9
                        ))
                    }
                }
            }
        }

        return attachments
    }

    // MARK: - Helper Methods

    private static func extractWithPattern(_ pattern: String, type: ExtractedEntity.EntityType, from text: String) -> [ExtractedEntity] {
        var entities: [ExtractedEntity] = []

        guard let regex = try? NSRegularExpression(pattern: pattern) else {
            return entities
        }

        let range = NSRange(text.startIndex..., in: text)
        let matches = regex.matches(in: text, range: range)

        for match in matches {
            if let range = Range(match.range, in: text) {
                let value = String(text[range])
                entities.append(ExtractedEntity(
                    type: type,
                    value: value,
                    range: range,
                    confidence: 0.95
                ))
            }
        }

        return entities
    }

    /// Search for entities matching a query
    static func searchEntities(in text: String, query: String, types: [ExtractedEntity.EntityType]? = nil) -> [ExtractedEntity] {
        let entities = extract(from: text)

        let filtered: [ExtractedEntity]
        if let types = types {
            filtered = entities.filter { types.contains($0.type) }
        } else {
            filtered = entities
        }

        // Case-insensitive search
        let lowercaseQuery = query.lowercased()
        return filtered.filter { $0.value.lowercased().contains(lowercaseQuery) }
    }
}
