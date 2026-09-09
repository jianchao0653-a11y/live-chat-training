import XCTest

final class AssistantUITests: XCTestCase {
    func testApprovalResetsAfterEditingAndDisconnectClearsText() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(zh-Hans)"]
        app.launch()
        XCTAssertTrue(app.textFields["endpoint"].waitForExistence(timeout: 10))
        let initial = XCTAttachment(screenshot: app.screenshot())
        initial.name = "connection-page-ready"; initial.lifetime = .keepAlways; add(initial)
        let transcript = app.textViews["transcript"]
        for _ in 0..<5 where !transcript.isHittable { app.swipeUp() }
        transcript.tap(); transcript.typeText("synthetic first message")
        app.buttons["finishInput"].tap()
        XCTAssertEqual(transcript.value as? String, "synthetic first message")
        let approval = app.switches["approval"]
        for _ in 0..<5 where !approval.isHittable { app.swipeUp() }
        XCTAssertTrue(approval.isHittable)
        approval.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        XCTAssertEqual(approval.value as? String, "1")
        for _ in 0..<5 where !transcript.isHittable { app.swipeDown() }
        transcript.tap(); transcript.typeText(" updated")
        app.buttons["finishInput"].tap()
        XCTAssertEqual(approval.value as? String, "0")
        let disconnect = app.buttons["disconnect"]
        for _ in 0..<8 where !disconnect.isHittable { app.swipeDown() }
        disconnect.tap()
        for _ in 0..<5 where !transcript.isHittable { app.swipeUp() }
        XCTAssertTrue(transcript.exists)
        XCTAssertEqual(transcript.value as? String, "")
        let capture = XCTAttachment(screenshot: app.screenshot()); capture.lifetime = .keepAlways; add(capture)
    }
}
