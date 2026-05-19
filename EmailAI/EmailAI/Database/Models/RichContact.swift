import Foundation
import GRDB

/// Contact source types
enum ContactSource: String, Codable {
    case gmail = "gmail"
    case apple = "apple"
    case outlook = "outlook"
    case manual = "manual"
}

/// Relationship type for VIP contacts
enum RelationshipType: String, Codable, CaseIterable {
    case vip = "vip"
    case family = "family"
    case important = "important"
    case colleague = "colleague"
    case friend = "friend"

    var displayName: String {
        switch self {
        case .vip: return "VIP"
        case .family: return "Family"
        case .important: return "Important"
        case .colleague: return "Colleague"
        case .friend: return "Friend"
        }
    }
}

/// Attribute types for contacts
enum ContactAttributeType: String, Codable {
    case hobby = "hobby"
    case interest = "interest"
    case skill = "skill"
    case project = "project"
}

/// VIP contact information
struct VIPContactInfo: Codable {
    let relationshipType: RelationshipType
    let relationshipScore: Int // 1-10
    let isPushEnabled: Bool
    let isPullEnabled: Bool
    let frequencyScore: Double

    init(
        relationshipType: RelationshipType = .vip,
        relationshipScore: Int = 8,
        isPushEnabled: Bool = true,
        isPullEnabled: Bool = true,
        frequencyScore: Double = 0.0
    ) {
        self.relationshipType = relationshipType
        self.relationshipScore = relationshipScore
        self.isPushEnabled = isPushEnabled
        self.isPullEnabled = isPullEnabled
        self.frequencyScore = frequencyScore
    }
}

/// Contact attribute (hobbies, interests, etc.)
struct ContactAttribute: Identifiable, Codable {
    var id: Int64?
    var contactId: Int64
    let type: ContactAttributeType
    let value: String

    init(id: Int64? = nil, contactId: Int64, type: ContactAttributeType, value: String) {
        self.id = id
        self.contactId = contactId
        self.type = type
        self.value = value
    }
}

/// Rich contact model with multi-source aggregation
struct RichContact: Identifiable, Codable {
    var id: Int64?
    let email: String
    let name: String?
    let displayName: String?
    let phone: String?
    let photoUrl: String?
    let source: ContactSource
    let company: String?
    let title: String?
    let location: String?
    let linkedinUrl: String?
    let twitterUrl: String?
    let notes: String?
    let vipInfo: VIPContactInfo?
    let attributes: [ContactAttribute]
    let overallScore: Double

    init(
        id: Int64? = nil,
        email: String,
        name: String? = nil,
        displayName: String? = nil,
        phone: String? = nil,
        photoUrl: String? = nil,
        source: ContactSource = .manual,
        company: String? = nil,
        title: String? = nil,
        location: String? = nil,
        linkedinUrl: String? = nil,
        twitterUrl: String? = nil,
        notes: String? = nil,
        vipInfo: VIPContactInfo? = nil,
        attributes: [ContactAttribute] = [],
        overallScore: Double = 0.0
    ) {
        self.id = id
        self.email = email
        self.name = name
        self.displayName = displayName
        self.phone = phone
        self.photoUrl = photoUrl
        self.source = source
        self.company = company
        self.title = title
        self.location = location
        self.linkedinUrl = linkedinUrl
        self.twitterUrl = twitterUrl
        self.notes = notes
        self.vipInfo = vipInfo
        self.attributes = attributes
        self.overallScore = overallScore
    }
}

// MARK: - Database Mappings

extension RichContact: FetchableRecord, MutablePersistableRecord {
    enum Columns {
        static let id = Column(CodingKeys.id)
        static let email = Column(CodingKeys.email)
        static let name = Column(CodingKeys.name)
        static let displayName = Column(CodingKeys.displayName)
        static let phone = Column(CodingKeys.phone)
        static let photoUrl = Column(CodingKeys.photoUrl)
        static let source = Column(CodingKeys.source)
        static let company = Column(CodingKeys.company)
        static let title = Column(CodingKeys.title)
        static let location = Column(CodingKeys.location)
        static let linkedinUrl = Column(CodingKeys.linkedinUrl)
        static let twitterUrl = Column(CodingKeys.twitterUrl)
        static let notes = Column(CodingKeys.notes)
    }

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}

extension ContactAttribute: FetchableRecord, MutablePersistableRecord {
    enum Columns {
        static let id = Column(CodingKeys.id)
        static let contactId = Column(CodingKeys.contactId)
        static let type = Column(CodingKeys.type)
        static let value = Column(CodingKeys.value)
    }

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}
