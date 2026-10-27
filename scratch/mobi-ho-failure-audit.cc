/*
 * Copyright (c) 2012-2018 Centre Tecnologic de Telecomunicacions de Catalunya (CTTC)
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Author: Manuel Requena <manuel.requena@cttc.es>
 */

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/lte-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/seq-ts-header.h"
#include <fstream>
#include <iomanip>
#include <cmath>
#include <map>
#include <vector>
#include <string>
// #include "ns3/gtk-config-store.h"
static std::ofstream radioCsv;
static std::ofstream handoverCsv;
static std::ofstream flowMetadataCsv;
struct RadioRecord
{
    double time;
    uint64_t imsi;
    uint16_t measuredCellId;
    double rsrp;
    double rsrq;
    bool isServingCell;
};

static std::vector<RadioRecord> radioRecords;

static std::map<std::string, uint64_t> ueContextPrefixes;


static void
WriteHandoverEvent(double time,
                   uint64_t imsi,
                   uint16_t cellId,
                   const std::string& event,
                   int targetCellId = -1)
{
    if (handoverCsv.is_open())
    {
        handoverCsv << std::fixed << std::setprecision(6)
                    << time << ","
                    << imsi << ","
                    << cellId << ","
                    << event << ",";

        if (targetCellId >= 0)
        {
            handoverCsv << targetCellId;
        }

        handoverCsv << "\n";
    }
}
using namespace ns3;
// Latest radio measurement for one UE/cell pair.
struct LiveRadioMeasurement
{
    double rsrpDbm;
    double rsrqDb;
    double timeSeconds;
};

static std::map<
    uint64_t,
    std::map<uint16_t, LiveRadioMeasurement>
> liveRadioMeasurements;
// Previous measurements for calculating RSRP trends.
static std::map<
    uint64_t,
    std::map<uint16_t, LiveRadioMeasurement>
> previousRadioMeasurements;

// Latest recorded mobility state for each UE.
static std::map<uint64_t, double> latestMobilityTime;
static std::map<uint64_t, double> latestMobilitySpeedMps;

// Keeps track of the candidate while we wait for it
// to remain stronger for a sustained period.
static std::map<uint64_t, uint16_t> candidateCells;
static std::map<uint64_t, double> candidateSince;
static std::map<uint64_t, double> lastHandoverRequest;
// Paired-action pilot state
static std::string g_pilotAction = "none";
static uint32_t g_pilotBoundary = 1;
static double g_pilotDecisionTime = -1.0;

static bool g_pilotActivated = false;
static double g_pilotHoldUntil = -1.0;



struct HandoverAttempt
{
    uint64_t attemptId;
    uint16_t sourceCell;
    uint16_t targetCell;
};

static std::ofstream canonicalHandoverCsv;
static std::map<uint64_t, HandoverAttempt> activeHandovers;
static uint64_t nextAttemptId = 0;

void
RecordHandoverStart(uint64_t imsi,
                    uint16_t sourceCell,
                    uint16_t targetCell)
{
    NS_ABORT_MSG_IF(
        activeHandovers.count(imsi) != 0,
        "Overlapping handover attempts"
    );

    HandoverAttempt attempt{
        ++nextAttemptId, sourceCell, targetCell
    };

    activeHandovers[imsi] = attempt;

    canonicalHandoverCsv
        << std::fixed << std::setprecision(6)
        << Simulator::Now().GetSeconds() << ","
        << imsi << ","
        << attempt.attemptId << ","
        << sourceCell << ","
        << targetCell << ",START,\n";
}

void
RecordHandoverTerminal(uint64_t imsi,
                       const std::string& event,
                       const std::string& reason = "")
{
    auto it = activeHandovers.find(imsi);

    if (it == activeHandovers.end())
    {
        std::cerr << "Ignoring unmatched handover "
                  << event << " for IMSI " << imsi
                  << std::endl;
        return;
    }

    const HandoverAttempt& attempt = it->second;

    canonicalHandoverCsv
        << std::fixed << std::setprecision(6)
        << Simulator::Now().GetSeconds() << ","
        << imsi << ","
        << attempt.attemptId << ","
        << attempt.sourceCell << ","
        << attempt.targetCell << ","
        << event << ","
        << reason << "\n";

    activeHandovers.erase(it);
}



void
NotifyRadioMeasurement(std::string context,
                       uint16_t rnti,
                       uint16_t cellId,
                       double rsrp,
                       double rsrq,
                       bool isServingCell,
                       uint8_t componentCarrierId)
{
    if (!radioCsv.is_open())
    {
        return;
    }

    radioCsv << std::fixed << std::setprecision(6)
             << Simulator::Now().GetSeconds() << ","
             << context << ","
             << rnti << ","
             << cellId << ","
             << rsrp << ","
             << rsrq << ","
             << (isServingCell ? 1 : 0) << ","
             << static_cast<unsigned int>(componentCarrierId)
             << "\n";
             
    // Version 1 exports the primary component carrier only.
    if (componentCarrierId != 0)
    {
        return;
    }

    uint64_t imsi = 0;

    for (const auto& entry : ueContextPrefixes)
    {
        if (context.rfind(entry.first, 0) == 0)
        {
            imsi = entry.second;
            break;
        }
    }
    if (imsi == 0)
{
    std::cerr << "DEBUG: Radio callback context = "
              << context << std::endl;

    std::cerr << "DEBUG: Registered UE prefixes:"
              << std::endl;

    for (const auto& entry : ueContextPrefixes)
    {
        std::cerr << "  Prefix: [" << entry.first
                  << "] IMSI: " << entry.second
                  << std::endl;
    }
}
    NS_ABORT_MSG_IF(
        imsi == 0,
        "Cannot identify IMSI from UE PHY context: " << context
    );

    radioRecords.push_back({
        Simulator::Now().GetSeconds(),
        imsi,
        cellId,
        rsrp,
        rsrq,
        isServingCell
    });
    // Preserve the preceding measurement before updating it.
    auto& measurements = liveRadioMeasurements[imsi];

    auto oldReading = measurements.find(cellId);

    if (oldReading != measurements.end())
 {
     previousRadioMeasurements[imsi][cellId] =
         oldReading->second;
 }

   // Update the latest live radio measurement.
    measurements[cellId] = {
     rsrp,
     rsrq,
     Simulator::Now().GetSeconds()
  };

}

static std::ofstream mobilityCsv;
// Output file for paired-action ML decision features.
static std::ofstream pilotDecisionCsv;
void
EvaluateRuleBasedHandover(
    Ptr<LteHelper> lteHelper,
    Ptr<NetDevice> ueDev,
    NetDeviceContainer enbDevs,
    Time interval)
{
    const double now = Simulator::Now().GetSeconds();

    // Re-evaluate periodically while the simulation is running.
    Simulator::Schedule(
        interval,
        &EvaluateRuleBasedHandover,
        lteHelper,
        ueDev,
        enbDevs,
        interval
    );

    Ptr<LteUeNetDevice> ue =
        DynamicCast<LteUeNetDevice>(ueDev);

    if (!ue || !ue->GetRrc())
    {
        return;
    }

    Ptr<LteUeRrc> rrc = ue->GetRrc();

    // Never request a handover during connection establishment
    // or while another handover is executing.
    if (rrc->GetState() != LteUeRrc::CONNECTED_NORMALLY)
    {
        return;
    }

    const uint64_t imsi = ue->GetImsi();
    const uint16_t servingCell = rrc->GetCellId();
    
    // Record the common pre-action feature snapshot.
    const bool pilotDecisionNow =
        (g_pilotAction == "stay" ||
         g_pilotAction == "handover") &&
        !g_pilotActivated &&
        std::abs(now - g_pilotDecisionTime) < 1e-6 &&
        servingCell == g_pilotBoundary;

    if (pilotDecisionNow)
    {
        auto ueIt = liveRadioMeasurements.find(imsi);
        auto mobilityIt = latestMobilityTime.find(imsi);
        auto speedIt = latestMobilitySpeedMps.find(imsi);

        if (ueIt == liveRadioMeasurements.end() ||
            mobilityIt == latestMobilityTime.end() ||
            speedIt == latestMobilitySpeedMps.end())
        {
            std::cerr << "PILOT FEATURES: missing measurements\n";
        }
        else
        {
            const auto& readings = ueIt->second;
            auto servingIt = readings.find(servingCell);

            if (servingIt == readings.end() ||
                now - servingIt->second.timeSeconds > 0.2)
            {
                std::cerr << "PILOT FEATURES: serving RSRP missing or stale\n";
            }
            else
            {
                const double servingRsrp = servingIt->second.rsrpDbm;
                uint16_t candidateCell = 0;
                double candidateRsrp = -1e9;

                for (const auto& entry : readings)
                {
                    if (entry.first == servingCell ||
                        now - entry.second.timeSeconds > 0.2)
                    {
                        continue;
                    }

                    if (entry.second.rsrpDbm > candidateRsrp)
                    {
                        candidateCell = entry.first;
                        candidateRsrp = entry.second.rsrpDbm;
                    }
                }

                const double mobilityAge = now - mobilityIt->second;

                if (candidateCell == 0 ||
                    mobilityAge < 0.0 ||
                    mobilityAge > 0.2)
                {
                    std::cerr << "PILOT FEATURES: candidate or mobility unavailable\n";
                }
                else
                {
                    const double delta = candidateRsrp - servingRsrp;
                    double slope = 0.0;
                    int trendAvailable = 0;

                    auto historyIt = previousRadioMeasurements.find(imsi);

                    if (historyIt != previousRadioMeasurements.end())
                    {
                        const auto& history = historyIt->second;
                        auto oldServing = history.find(servingCell);
                        auto oldCandidate = history.find(candidateCell);

                        if (oldServing != history.end() &&
                            oldCandidate != history.end())
                        {
                            const double previousDelta =
                                oldCandidate->second.rsrpDbm -
                                oldServing->second.rsrpDbm;

                            const double currentTimestamp =
                                std::max(servingIt->second.timeSeconds,
                                         readings.at(candidateCell).timeSeconds);

                            const double previousTimestamp =
                                std::max(oldServing->second.timeSeconds,
                                         oldCandidate->second.timeSeconds);

                            const double dt =
                                currentTimestamp - previousTimestamp;

                            if (dt > 1e-9)
                            {
                                slope = (delta - previousDelta) / dt;
                                trendAvailable = 1;
                            }
                        }
                    }

                    pilotDecisionCsv
                        << std::fixed << std::setprecision(6)
                        << now << ","
                        << imsi << ","
                        << servingCell << ","
                        << candidateCell << ","
                        << servingRsrp << ","
                        << candidateRsrp << ","
                        << delta << ","
                        << slope << ","
                        << trendAvailable << ","
                        << speedIt->second << ","
                        << mobilityAge << ","
                        << g_pilotAction << "\n";

                    std::cout
                        << "PILOT FEATURES RECORDED"
                        << " time=" << now
                        << " candidate=" << candidateCell
                        << " delta=" << delta
                        << " slope=" << slope
                        << " trend_available=" << trendAvailable
                        << std::endl;
                }
            }
        }
    }

    // True only at the forced HANDOVER decision point.
    const bool pilotHandoverNow =
      g_pilotAction == "handover" &&
      !g_pilotActivated &&
      std::abs(now - g_pilotDecisionTime) < 1e-6 &&
      servingCell == g_pilotBoundary;
    // Pilot STAY branch: suppress normal handover decisions
   // for 200 ms starting at the specified decision time.

   if (g_pilotAction == "stay")
  {
      const double epsilon = 1e-6;

      if (!g_pilotActivated &&
         std::abs(now - g_pilotDecisionTime) < epsilon &&
         servingCell == g_pilotBoundary)
     {
         g_pilotActivated = true;
         g_pilotHoldUntil = now + 0.2;

         std::cout
             << "PILOT DECISION: STAY"
             << " time=" << now
             << " IMSI=" << imsi
             << " serving=" << servingCell
             << " hold_until=" << g_pilotHoldUntil
             << std::endl;
     }

     if (g_pilotActivated && now < g_pilotHoldUntil)
    {
         return;
     }
 } 
   // Prevent additional normal decisions during the 
  // HANDOVER branch's 200 ms action interval.
  if (g_pilotAction == "handover" &&
     g_pilotActivated &&
     now < g_pilotHoldUntil)
 {
     return;
 }
   // Pilot HANDOVER branch: request the selected neighbour
  // at the configured decision timestamp.

//   if (g_pilotAction == "handover" &&
//      !g_pilotActivated &&
//      std::abs(now - g_pilotDecisionTime) < 1e-6 &&
//      servingCell == g_pilotBoundary)
//  {
//      g_pilotActivated = true;
//      g_pilotHoldUntil = now + 0.2;

//      std::cout
 //        << "PILOT DECISION: HANDOVER"
//         << " time=" << now
//         << " IMSI=" << imsi
//         << " source=" << servingCell
//         << std::endl;

      // Suppress the normal controller during the forced-action
     // window. The explicit handover request will be added after
     // selecting and validating the candidate.
//     return;
// }
    if (activeHandovers.count(imsi) != 0)
    {
        return;
    }

    const double cooldownSeconds = 1.0;

    if (lastHandoverRequest.count(imsi) &&
        now - lastHandoverRequest[imsi] < cooldownSeconds)
    {
        return;
    }

    auto ueMeasurements = liveRadioMeasurements.find(imsi);

    if (ueMeasurements == liveRadioMeasurements.end())
    {
        return;
    }

    const auto& measurements = ueMeasurements->second;

    auto servingIt = measurements.find(servingCell);

    if (servingIt == measurements.end())
    {
        return;
    }

    const double maxMeasurementAge = 0.3;

    if (now - servingIt->second.timeSeconds >
        maxMeasurementAge)
    {
        return;
    }

    const double servingRsrp = servingIt->second.rsrpDbm;

    double bestRsrp = servingRsrp;
    uint16_t bestCell = servingCell;

    // Identify the strongest currently measured neighbour.
    for (const auto& item : measurements)
    {
        const uint16_t cellId = item.first;
        const LiveRadioMeasurement& reading = item.second;

        if (cellId == servingCell)
        {
            continue;
        }

        if (now - reading.timeSeconds > maxMeasurementAge)
        {
            continue;
        }

        if (reading.rsrpDbm > bestRsrp)
        {
            bestRsrp = reading.rsrpDbm;
            bestCell = cellId;
        }
    }

    
  const double rsrpMarginDb = 3.0;
  const double persistenceSeconds = 0.4;

  if (pilotHandoverNow)
  {
     // The pilot uses the strongest currently measured
     // eligible neighbour, without requiring the ordinary
     // rule controller's 400 ms persistence.
     if (bestCell == servingCell)
     {
         std::cout
             << "PILOT REJECTED: no stronger neighbour at t="
             << now << std::endl;
         return;
     }
 }
  else
  {
     // Normal rule-based follow-up behaviour.
     if (bestCell == servingCell ||
         bestRsrp - servingRsrp < rsrpMarginDb)
     {
         candidateCells.erase(imsi);
         candidateSince.erase(imsi);
         return;
     }

     if (!candidateCells.count(imsi) ||
         candidateCells[imsi] != bestCell)
     {
         candidateCells[imsi] = bestCell;
         candidateSince[imsi] = now;
         return;
     }

     if (now - candidateSince[imsi] < persistenceSeconds)
     {
         return;
     }
 }


    // Resolve the real source eNB from the UE's current RRC
    // serving cell, rather than assuming a fixed transition.
    Ptr<NetDevice> sourceEnb;
    bool targetExists = false;

    for (uint32_t i = 0; i < enbDevs.GetN(); ++i)
    {
        Ptr<LteEnbNetDevice> enb =
            DynamicCast<LteEnbNetDevice>(enbDevs.Get(i));

        if (!enb)
        {
            continue;
        }

        if (enb->GetCellId() == servingCell)
        {
            sourceEnb = enbDevs.Get(i);
        }

        if (enb->GetCellId() == bestCell)
        {
            targetExists = true;
        }
    }

    if (!sourceEnb || !targetExists)
    {
        return;
    }

    std::cout
        << "RULE CONTROLLER: t=" << now
        << " IMSI=" << imsi
        << " source=" << servingCell
        << " target=" << bestCell
        << " serving_RSRP=" << servingRsrp
        << " target_RSRP=" << bestRsrp
        << std::endl;
    if (pilotHandoverNow)
{
    g_pilotActivated = true;
    g_pilotHoldUntil = now + 0.2;

    std::cout
        << "PILOT DECISION: HANDOVER"
        << " time=" << now
        << " IMSI=" << imsi
        << " source=" << servingCell
        << " target=" << bestCell
        << " serving_RSRP=" << servingRsrp
        << " target_RSRP=" << bestRsrp
        << std::endl;
}
    // HandoverRequest uses a relative scheduling delay.
    lteHelper->HandoverRequest(
        MilliSeconds(1),
        ueDev,
        sourceEnb,
        bestCell
    );

    lastHandoverRequest[imsi] = now;
    candidateCells.erase(imsi);
    candidateSince.erase(imsi);
}


static std::ofstream trafficCsv;

static std::ofstream packetsCsv;

void
LogPacketRxDetailed(uint64_t imsi,
                    std::string flowId,
                    std::string direction,
                    Ptr<const Packet> packet,
                    const Address& from)
{
    if (!packetsCsv.is_open())
    {
        return;
    }

    SeqTsHeader seqHeader;

    uint32_t headerBytes = seqHeader.GetSerializedSize();

    NS_ABORT_MSG_IF(
        packet->GetSize() < headerBytes,
        "Received UDP packet is too small for SeqTsHeader"
    );

    // Read the real application sequence without altering
    // the packet seen by other trace callbacks.
    uint32_t bytesRead = packet->PeekHeader(seqHeader);

    NS_ABORT_MSG_IF(
        bytesRead != headerBytes,
        "Could not read UDP sequence header"
    );

    uint32_t sequence = seqHeader.GetSeq();

    // Exclude the SeqTsHeader metadata bytes.
    uint32_t payloadBytes = packet->GetSize() - headerBytes;

    packetsCsv << std::fixed << std::setprecision(6)
               << Simulator::Now().GetSeconds() << ","
               << imsi << ","
               << flowId << ","
               << direction << ","
               << sequence << ","
               << payloadBytes << "\n";
}


void
LogPacketRx(std::string direction,
            Ptr<const Packet> packet,
            const Address& from)
{
    if (!trafficCsv.is_open())
    {
        return;
    }

    trafficCsv << std::fixed << std::setprecision(6)
               << Simulator::Now().GetSeconds() << ","
               << direction << ","
               << packet->GetSize() << "\n";
}


void
LogMobility(Ptr<Node> ue, uint64_t imsi, Time interval)
{
    Ptr<MobilityModel> model = ue->GetObject<MobilityModel>();

    if (model == nullptr)
    {
        return;
    }

    Vector position = model->GetPosition();
    Vector velocity = model->GetVelocity();

    double speedMps = std::sqrt(
        velocity.x * velocity.x +
        velocity.y * velocity.y +
        velocity.z * velocity.z
    );

    double speedKmh = speedMps * 3.6;
    // Preserve the latest mobility observation for ML features.
    latestMobilityTime[imsi] =
      Simulator::Now().GetSeconds();

    latestMobilitySpeedMps[imsi] = speedMps;

    if (mobilityCsv.is_open())
    {
        mobilityCsv << std::fixed << std::setprecision(6)
                    << Simulator::Now().GetSeconds() << ","
                    << imsi << ","
                    << position.x << ","
                    << position.y << ","
                    << position.z << ","
                    << speedMps << ","
                    << speedKmh << "\n";
    }

    Simulator::Schedule(
        interval,
        &LogMobility,
        ue,
        imsi,
        interval
    );
}




NS_LOG_COMPONENT_DEFINE("LenaX2HandoverExample");
// UE-side failure-event instrumentation.
// Keep separate from handover outcome accounting.
static std::ofstream g_serviceEventsCsv;

void
WriteServiceEvent(double timeSeconds,
                  uint64_t imsi,
                  uint16_t cellId,
                  const std::string& eventType,
                  int detail = -1)
{
    if (!g_serviceEventsCsv.is_open())
    {
        return;
    }

    g_serviceEventsCsv
        << std::fixed << std::setprecision(6)
        << timeSeconds << ","
        << imsi << ","
        << cellId << ","
        << eventType << ",";

    if (detail >= 0)
    {
        g_serviceEventsCsv << detail;
    }

    g_serviceEventsCsv << "\n";
}

void
NotifyRadioLinkFailure(std::string context,
                       uint64_t imsi,
                       uint16_t cellId,
                       uint16_t rnti)
{
    (void)context;
    (void)rnti;

    WriteServiceEvent(
        Simulator::Now().GetSeconds(),
        imsi,
        cellId,
        "RADIO_LINK_FAILURE");

    std::cout << "SERVICE EVENT: RADIO_LINK_FAILURE"
              << " time=" << Simulator::Now().GetSeconds()
              << " imsi=" << imsi
              << " cell=" << cellId << std::endl;
}

void
NotifyConnectionTimeout(std::string context,
                        uint64_t imsi,
                        uint16_t cellId,
                        uint16_t rnti,
                        uint8_t count)
{
    (void)context;
    (void)rnti;

    WriteServiceEvent(
        Simulator::Now().GetSeconds(),
        imsi,
        cellId,
        "CONNECTION_TIMEOUT",
        static_cast<int>(count));

    std::cout << "SERVICE EVENT: CONNECTION_TIMEOUT"
              << " time=" << Simulator::Now().GetSeconds()
              << " imsi=" << imsi
              << " cell=" << cellId
              << " count=" << static_cast<int>(count)
              << std::endl;
}

/**
 * UE Connection established notification.
 *
 * @param context The context.
 * @param imsi The IMSI of the connected terminal.
 * @param cellid The Cell ID.
 * @param rnti The RNTI.
 */
void
NotifyConnectionEstablishedUe(std::string context, uint64_t imsi, uint16_t cellid, uint16_t rnti)
{
    std::cout << Simulator::Now().As(Time::S) << " " << context << " UE IMSI " << imsi
              << ": connected to CellId " << cellid << " with RNTI " << rnti << std::endl;
     WriteHandoverEvent(
    Simulator::Now().GetSeconds(),
    imsi,
    cellid,
    "CONNECTION_ESTABLISHED");
}

/**
 * UE Start Handover notification.
 *
 * @param context The context.
 * @param imsi The IMSI of the connected terminal.
 * @param cellid The actual Cell ID.
 * @param rnti The RNTI.
 * @param targetCellId The target Cell ID.
 */
void
NotifyHandoverStartUe(std::string context,
                      uint64_t imsi,
                      uint16_t cellid,
                      uint16_t rnti,
                      uint16_t targetCellId)
{
    std::cout << Simulator::Now().As(Time::S) << " " << context << " UE IMSI " << imsi
              << ": previously connected to CellId " << cellid << " with RNTI " << rnti
              << ", doing handover to CellId " << targetCellId << std::endl;
     RecordHandoverStart(imsi, cellid, targetCellId);
     WriteHandoverEvent(
    Simulator::Now().GetSeconds(),
    imsi,
    cellid,
    "HO_START",
    targetCellId);
}

/**
 * UE Handover end successful notification.
 *
 * @param context The context.
 * @param imsi The IMSI of the connected terminal.
 * @param cellid The Cell ID.
 * @param rnti The RNTI.
 */
void
NotifyHandoverEndOkUe(std::string context, uint64_t imsi, uint16_t cellid, uint16_t rnti)
{
    std::cout << Simulator::Now().As(Time::S) << " " << context << " UE IMSI " << imsi
              << ": successful handover to CellId " << cellid << " with RNTI " << rnti << std::endl;
     RecordHandoverTerminal(imsi, "SUCCESS");
     WriteHandoverEvent(
    Simulator::Now().GetSeconds(),
    imsi,
    cellid,
    "HO_SUCCESS");

}

/**
 * eNB Connection established notification.
 *
 * @param context The context.
 * @param imsi The IMSI of the connected terminal.
 * @param cellid The Cell ID.
 * @param rnti The RNTI.
 */
void
NotifyConnectionEstablishedEnb(std::string context, uint64_t imsi, uint16_t cellid, uint16_t rnti)
{
    std::cout << Simulator::Now().As(Time::S) << " " << context << " eNB CellId " << cellid
              << ": successful connection of UE with IMSI " << imsi << " RNTI " << rnti
              << std::endl;
}

/**
 * eNB Start Handover notification.
 *
 * @param context The context.
 * @param imsi The IMSI of the connected terminal.
 * @param cellid The actual Cell ID.
 * @param rnti The RNTI.
 * @param targetCellId The target Cell ID.
 */
void
NotifyHandoverStartEnb(std::string context,
                       uint64_t imsi,
                       uint16_t cellid,
                       uint16_t rnti,
                       uint16_t targetCellId)
{
    std::cout << Simulator::Now().As(Time::S) << " " << context << " eNB CellId " << cellid
              << ": start handover of UE with IMSI " << imsi << " RNTI " << rnti << " to CellId "
              << targetCellId << std::endl;
}

/**
 * eNB Handover end successful notification.
 *
 * @param context The context.
 * @param imsi The IMSI of the connected terminal.
 * @param cellid The Cell ID.
 * @param rnti The RNTI.
 */
void
NotifyHandoverEndOkEnb(std::string context, uint64_t imsi, uint16_t cellid, uint16_t rnti)
{
    std::cout << Simulator::Now().As(Time::S) << " " << context << " eNB CellId " << cellid
              << ": completed handover of UE with IMSI " << imsi << " RNTI " << rnti << std::endl;
}

/**
 * Handover failure notification
 *
 * @param context The context.
 * @param imsi The IMSI of the connected terminal.
 * @param cellid The Cell ID.
 * @param rnti The RNTI.
 */
void
NotifyHandoverFailure(std::string reason,std::string context, uint64_t imsi, uint16_t cellid, uint16_t rnti)
{
    std::cout << Simulator::Now().As(Time::S) << " " << context << " eNB CellId " << cellid
              << " IMSI " << imsi << " RNTI " << rnti << " handover failure" << std::endl;
     RecordHandoverTerminal(imsi, "FAILURE", reason);
     WriteHandoverEvent(
    Simulator::Now().GetSeconds(),
    imsi,
    cellid,
    "HO_FAILURE");
}

/**
 * Sample simulation script for a X2-based handover.
 * It instantiates two eNodeB, attaches one UE to the 'source' eNB and
 * triggers a handover of the UE towards the 'target' eNB.
 */
int
main(int argc, char* argv[])
{
     g_serviceEventsCsv.open("service_events.csv", std::ios::out);

     g_serviceEventsCsv
          << "time_s,imsi,cell_id,event_type,detail\n";
     // LogLevel logLevel = (LogLevel)(LOG_PREFIX_FUNC | LOG_PREFIX_TIME | LOG_LEVEL_ALL);

    // LogComponentEnable ("LteHelper", logLevel);
    // LogComponentEnable ("EpcHelper", logLevel);
    // LogComponentEnable ("EpcEnbApplication", logLevel);
    // LogComponentEnable ("EpcMmeApplication", logLevel);
    // LogComponentEnable ("EpcPgwApplication", logLevel);
    // LogComponentEnable ("EpcSgwApplication", logLevel);
    // LogComponentEnable ("EpcX2", logLevel);

    // LogComponentEnable ("LteEnbRrc", logLevel);
    // LogComponentEnable ("LteEnbNetDevice", logLevel);
    // LogComponentEnable ("LteUeRrc", logLevel);
    // LogComponentEnable ("LteUeNetDevice", logLevel);

    uint16_t numberOfUes = 1;
    uint16_t numberOfEnbs = 3;
    uint16_t numBearersPerUe = 2;
    Time simTime = MilliSeconds(490);
    double distance = 200.0;
    double speedKmh = 30.0;
    bool disableDl = false;
    bool disableUl = false;
    uint32_t rngSeed = 1;
    uint64_t rngRun = 1;

    // change some default attributes so that they are reasonable for
    // this scenario, but do this before processing command line
    // arguments, so that the user is allowed to override these settings
    Config::SetDefault("ns3::UdpClient::Interval", TimeValue(MilliSeconds(10)));
    Config::SetDefault("ns3::UdpClient::MaxPackets", UintegerValue(1000000));
    Config::SetDefault("ns3::LteHelper::UseIdealRrc", BooleanValue(false));

    // Command line arguments
    CommandLine cmd(__FILE__);
    // Paired-action experiment configuration
    std::string pilotAction = "none";
    uint32_t pilotBoundary = 1;
    double pilotDecisionTime = -1.0;
    cmd.AddValue("numberOfUes", "Number of UEs", numberOfUes);
    cmd.AddValue("numberOfEnbs", "Number of eNodeBs", numberOfEnbs);
    cmd.AddValue("speedKmh", "UE speed in km/h", speedKmh);
    cmd.AddValue("rngSeed", "ns-3 random seed", rngSeed);
    cmd.AddValue("rngRun", "ns-3 random run number", rngRun);
    cmd.AddValue(
      "pilotAction",
      "Pilot action: none, stay, or handover",
      pilotAction
     );

    cmd.AddValue(
      "pilotBoundary",
      "Cell boundary: 1 or 2",
      pilotBoundary
     );

    cmd.AddValue(
      "pilotDecisionTime",
      "Forced-action decision time in seconds",
      pilotDecisionTime
     );
    cmd.AddValue("disableDl", "Disable downlink data flows", disableDl);
    cmd.AddValue("disableUl", "Disable uplink data flows", disableUl);
    cmd.Parse(argc, argv);
    g_pilotAction = pilotAction;
    g_pilotBoundary = pilotBoundary;
    g_pilotDecisionTime = pilotDecisionTime;
    // Create the ML feature output file.
    pilotDecisionCsv.open(
     "pilot_decision_features.csv",
     std::ios::out | std::ios::trunc
 );

    NS_ABORT_MSG_IF(
      !pilotDecisionCsv.is_open(),
      "Cannot open pilot_decision_features.csv"
  );

    pilotDecisionCsv
     << "decision_time_s,"
     << "imsi,"
     << "serving_cell_id,"
     << "candidate_cell_id,"
     << "serving_rsrp_dbm,"
     << "candidate_rsrp_dbm,"
     << "rsrp_delta_db,"
     << "delta_slope_db_per_s,"
     << "trend_available,"
     << "speed_mps,"
     << "mobility_age_s,"
     << "pilot_action\n";
    NS_ABORT_MSG_IF(
        pilotAction != "none" &&
        pilotAction != "stay" &&
        pilotAction != "handover",
       "Invalid pilotAction"
     );

    NS_ABORT_MSG_IF(
       pilotBoundary != 1 && pilotBoundary != 2,
      "pilotBoundary must be 1 or 2"
      );

    NS_ABORT_MSG_IF(
      pilotAction != "none" && pilotDecisionTime < 0.0,
      "Pilot action requires a decision time"
     );

   std::cout << "Pilot action: " << pilotAction << "\n";
   std::cout << "Pilot boundary: " << pilotBoundary << "\n";
   std::cout << "Pilot decision time: "
          << pilotDecisionTime << "\n";
    NS_ABORT_MSG_IF(rngSeed == 0, "RNG seed must be positive");
    NS_ABORT_MSG_IF(rngRun == 0, "RNG run must be positive");

    RngSeedManager::SetSeed(rngSeed);
    RngSeedManager::SetRun(rngRun);

    std::cout << "RNG seed: " << rngSeed << "\n";
    std::cout << "RNG run: " << rngRun << "\n";
    radioCsv.open("radio_measurements.csv",
                  std::ios::out | std::ios::trunc);

    NS_ABORT_MSG_IF(!radioCsv.is_open(),
                    "Cannot open radio_measurements.csv");

    radioCsv << "time_s,ue_context,rnti,measured_cell_id,"
                "rsrp_dbm,rsrq_db,is_serving_cell,carrier_id\n";

    handoverCsv.open("handover_events.csv",std::ios::out | std::ios::trunc);
    NS_ABORT_MSG_IF(!handoverCsv.is_open(),
    "Could not open handover_events.csv");
    handoverCsv
    << "time_s,imsi,cell_id,event,target_cell_id\n";
    canonicalHandoverCsv.open(
        "handovers.csv",
      std::ios::out | std::ios::trunc
    );

    NS_ABORT_MSG_IF(
      !canonicalHandoverCsv.is_open(),
      "Cannot open handovers.csv"
    );

    canonicalHandoverCsv
      << "time_s,imsi,attempt_id,source_cell_id,"
         "target_cell_id,event,failure_reason\n";
    NS_ABORT_MSG_IF(speedKmh <= 0.0, "Speed must be positive");
    simTime = Seconds(450.0 / (speedKmh / 3.6) + 2.0);
    mobilityCsv.open("mobility.csv", std::ios::out | std::ios::trunc);
    

    NS_ABORT_MSG_IF(
    !mobilityCsv.is_open(),
    "Cannot open mobility.csv"
    );

    mobilityCsv << "time_s,imsi,x_m,y_m,z_m,speed_mps,speed_kmh\n";
    
    trafficCsv.open("traffic_rx.csv",
                std::ios::out | std::ios::trunc);

    NS_ABORT_MSG_IF(
        !trafficCsv.is_open(),
     "Cannot open traffic_rx.csv"
    );

    trafficCsv << "time_s,direction,packet_size_bytes\n";
    packetsCsv.open("packets.csv", std::ios::out | std::ios::trunc);

    NS_ABORT_MSG_IF(
       !packetsCsv.is_open(),
       "Cannot open packets.csv"
    );

    packetsCsv
       << "time_s,imsi,flow_id,direction,sequence,payload_bytes\n";
    // Initialize traffic flow metadata
    flowMetadataCsv.open(
       "traffic.csv",
       std::ios::out | std::ios::trunc
     );

    NS_ABORT_MSG_IF(
       !flowMetadataCsv.is_open(),
       "Cannot open traffic.csv"
     );

    flowMetadataCsv
        << "imsi,flow_id,direction,packet_interval_s\n";

    Ptr<LteHelper> lteHelper = CreateObject<LteHelper>();
    Ptr<PointToPointEpcHelper> epcHelper = CreateObject<PointToPointEpcHelper>();
    lteHelper->SetEpcHelper(epcHelper);
    lteHelper->SetSchedulerType("ns3::RrFfMacScheduler");
    lteHelper->SetHandoverAlgorithmType(
        "ns3::NoOpHandoverAlgorithm");
    //lteHelper->SetHandoverAlgorithmAttribute(
      //  "Hysteresis", DoubleValue(3.0));
    //lteHelper->SetHandoverAlgorithmAttribute(
        //"TimeToTrigger", TimeValue(MilliSeconds(256)));

    Ptr<Node> pgw = epcHelper->GetPgwNode();

    // Create a single RemoteHost
    NodeContainer remoteHostContainer;
    remoteHostContainer.Create(1);
    Ptr<Node> remoteHost = remoteHostContainer.Get(0);
    InternetStackHelper internet;
    internet.Install(remoteHostContainer);

    // Create the Internet
    PointToPointHelper p2ph;
    p2ph.SetDeviceAttribute("DataRate", DataRateValue(DataRate("100Gb/s")));
    p2ph.SetDeviceAttribute("Mtu", UintegerValue(1500));
    p2ph.SetChannelAttribute("Delay", TimeValue(Seconds(0.010)));
    NetDeviceContainer internetDevices = p2ph.Install(pgw, remoteHost);
    Ipv4AddressHelper ipv4h;
    ipv4h.SetBase("1.0.0.0", "255.0.0.0");
    Ipv4InterfaceContainer internetIpIfaces = ipv4h.Assign(internetDevices);
    Ipv4Address remoteHostAddr = internetIpIfaces.GetAddress(1);

    // Routing of the Internet Host (towards the LTE network)
    Ipv4StaticRoutingHelper ipv4RoutingHelper;
    Ptr<Ipv4StaticRouting> remoteHostStaticRouting =
        ipv4RoutingHelper.GetStaticRouting(remoteHost->GetObject<Ipv4>());
    // interface 0 is localhost, 1 is the p2p device
    remoteHostStaticRouting->AddNetworkRouteTo(Ipv4Address("7.0.0.0"), Ipv4Mask("255.0.0.0"), 1);

    NodeContainer ueNodes;
    NodeContainer enbNodes;
    enbNodes.Create(numberOfEnbs);
    ueNodes.Create(numberOfUes);

    // MOBI-HO Lab: three fixed LTE cells
    Ptr<ListPositionAllocator> enbPositions =
        CreateObject<ListPositionAllocator>();

    for (uint16_t i = 0; i < numberOfEnbs; ++i)
    {
        enbPositions->Add(Vector(distance * i, 0.0, 0.0));
    }

    MobilityHelper enbMobility;
    enbMobility.SetPositionAllocator(enbPositions);
    enbMobility.SetMobilityModel(
        "ns3::ConstantPositionMobilityModel");
    enbMobility.Install(enbNodes);

    // Moving UE, initially positioned at Cell 1
    Ptr<ListPositionAllocator> uePositions =
        CreateObject<ListPositionAllocator>();

    for (uint16_t i = 0; i < numberOfUes; ++i)
    {
        uePositions->Add(Vector(0.0, 0.0, 0.0));
    }

    MobilityHelper ueMobility;
    ueMobility.SetPositionAllocator(uePositions);
    ueMobility.SetMobilityModel(
        "ns3::ConstantVelocityMobilityModel");
    ueMobility.Install(ueNodes);

    double speedMs = speedKmh / 3.6;

    for (uint16_t i = 0; i < numberOfUes; ++i)
    {
        Ptr<ConstantVelocityMobilityModel> model =
            ueNodes.Get(i)->GetObject<
                ConstantVelocityMobilityModel>();

        model->SetVelocity(Vector(speedMs, 0.0, 0.0));
    }

    std::cout << "MOBI-HO Lab - External Handover Controller Test\\n";
    std::cout << "Cells: " << numberOfEnbs << "\\n";
    std::cout << "UE speed: " << speedKmh << " km/h\\n";
    std::cout << "Simulation duration: "
              << simTime.GetSeconds() << " s\\n";

    // Install LTE Devices in eNB and UEs
    NetDeviceContainer enbLteDevs = lteHelper->InstallEnbDevice(enbNodes);
    
    NetDeviceContainer ueLteDevs = lteHelper->InstallUeDevice(ueNodes);

    for (uint32_t i = 0; i < ueNodes.GetN(); ++i)
   {
       Ptr<LteUeNetDevice> ueDevice =
          DynamicCast<LteUeNetDevice>(ueLteDevs.Get(i));

    NS_ABORT_MSG_IF(
        ueDevice == nullptr,
        "LTE UE device not found"
    );

    uint64_t imsi = ueDevice->GetImsi();

    // Register UE node ID and IMSI for radio measurements
    std::string prefix =
        "/NodeList/" +
        std::to_string(ueNodes.Get(i)->GetId()) +
        "/";

    ueContextPrefixes[prefix] = imsi;

    std::cout << "REGISTERED UE: "
              << prefix
              << " IMSI=" << imsi
              << std::endl;

    // Preserve existing mobility logging
    Simulator::Schedule(
        Seconds(0.0),
        &LogMobility,
        ueNodes.Get(i),
        imsi,
        MilliSeconds(200)
    );
}

    // Install the IP stack on the UEs
    internet.Install(ueNodes);
    Ipv4InterfaceContainer ueIpIfaces;
    ueIpIfaces = epcHelper->AssignUeIpv4Address(NetDeviceContainer(ueLteDevs));

    // Attach all UEs to the first eNodeB
    for (uint16_t i = 0; i < numberOfUes; i++)
    {
        lteHelper->Attach(ueLteDevs.Get(i), enbLteDevs.Get(0));
    }

    NS_LOG_LOGIC("setting up applications");

    // Install and start applications on UEs and remote host
    uint16_t dlPort = 10000;
    uint16_t ulPort = 20000;

    // randomize a bit start times to avoid simulation artifacts
    // (e.g., buffer overflows due to packet transmissions happening
    // exactly at the same time)
    Ptr<UniformRandomVariable> startTimeSeconds = CreateObject<UniformRandomVariable>();
    startTimeSeconds->SetAttribute("Min", DoubleValue(0.05));
    startTimeSeconds->SetAttribute("Max", DoubleValue(0.06));

    for (uint32_t u = 0; u < numberOfUes; ++u)
    {
        Ptr<Node> ue = ueNodes.Get(u);
        Ptr<LteUeNetDevice> ueDevice =
                     DynamicCast<LteUeNetDevice>(ueLteDevs.Get(u));

        NS_ABORT_MSG_IF(
             ueDevice == nullptr,
             "Cannot identify LTE UE for packet logging"
         );

        uint64_t packetImsi = ueDevice->GetImsi();
        // Set the default gateway for the UE
        Ptr<Ipv4StaticRouting> ueStaticRouting =
            ipv4RoutingHelper.GetStaticRouting(ue->GetObject<Ipv4>());
        ueStaticRouting->SetDefaultRoute(epcHelper->GetUeDefaultGatewayAddress(), 1);

        for (uint32_t b = 0; b < numBearersPerUe; ++b)
        {
            ApplicationContainer clientApps;
            ApplicationContainer serverApps;
            Ptr<EpcTft> tft = Create<EpcTft>();

            if (!disableDl)
            {
                ++dlPort;

                NS_LOG_LOGIC("installing UDP DL app for UE " << u);
                UdpClientHelper dlClientHelper(ueIpIfaces.GetAddress(u), dlPort);
                clientApps.Add(dlClientHelper.Install(remoteHost));
                PacketSinkHelper dlPacketSinkHelper(
                    "ns3::UdpSocketFactory",
                    InetSocketAddress(Ipv4Address::GetAny(), dlPort));
                serverApps.Add(dlPacketSinkHelper.Install(ue));
                
                Ptr<PacketSink> dlSink =
                   DynamicCast<PacketSink>(
                     serverApps.Get(serverApps.GetN() - 1)
                );

               NS_ABORT_MSG_IF(
                   dlSink == nullptr,
                   "Downlink PacketSink not found"
               );

               dlSink->TraceConnectWithoutContext(
                   "Rx",
                    MakeBoundCallback(
                    &LogPacketRx,
                    std::string("DL")
               )
            );
                
               std::string dlFlowId =
                 "ue" + std::to_string(packetImsi) +
                 "_dl_b" + std::to_string(b);
               flowMetadataCsv
                  << packetImsi << ","
                  << dlFlowId << ",DL,0.01\n";

              dlSink->TraceConnectWithoutContext(
                "Rx",
                MakeBoundCallback(
                  &LogPacketRxDetailed,
                  packetImsi,
                  dlFlowId,
                  std::string("DL")
              )
           );

                EpcTft::PacketFilter dlpf;
                dlpf.localPortStart = dlPort;
                dlpf.localPortEnd = dlPort;
                tft->Add(dlpf);
            }

            if (!disableUl)
            {
                ++ulPort;

                NS_LOG_LOGIC("installing UDP UL app for UE " << u);
                UdpClientHelper ulClientHelper(remoteHostAddr, ulPort);
                clientApps.Add(ulClientHelper.Install(ue));
                PacketSinkHelper ulPacketSinkHelper(
                    "ns3::UdpSocketFactory",
                    InetSocketAddress(Ipv4Address::GetAny(), ulPort));
                serverApps.Add(ulPacketSinkHelper.Install(remoteHost));
                
                
                Ptr<PacketSink> ulSink =
                   DynamicCast<PacketSink>(
                     serverApps.Get(serverApps.GetN() - 1)
                   );

                NS_ABORT_MSG_IF(
                   ulSink == nullptr,
                   "Downlink PacketSink not found" 
                    );

               ulSink->TraceConnectWithoutContext(
                  "Rx",
               MakeBoundCallback(
                 &LogPacketRx,
                 std::string("UL")
               )
           );
               
              std::string ulFlowId =
                "ue" + std::to_string(packetImsi) +
                "_ul_b" + std::to_string(b);
              flowMetadataCsv
                 << packetImsi << ","
                 << ulFlowId << ",UL,0.01\n";
              ulSink->TraceConnectWithoutContext(
                 "Rx",
              MakeBoundCallback(
                 &LogPacketRxDetailed,
                 packetImsi,
                 ulFlowId,
                 std::string("UL")
    )
);


                EpcTft::PacketFilter ulpf;
                ulpf.remotePortStart = ulPort;
                ulpf.remotePortEnd = ulPort;
                tft->Add(ulpf);
            }

            EpsBearer bearer(EpsBearer::NGBR_VIDEO_TCP_DEFAULT);
            lteHelper->ActivateDedicatedEpsBearer(ueLteDevs.Get(u), bearer, tft);

            Time startTime = Seconds(startTimeSeconds->GetValue());
            serverApps.Start(startTime);
            clientApps.Start(startTime);
            clientApps.Stop(simTime);
        }
    }

    // Add X2 interface
    lteHelper->AddX2Interface(enbNodes);
    // Start the live rule-based controller.
// This replaces the earlier scheduled/manual handover test.

    Simulator::Schedule(
      Seconds(0.5),
      &EvaluateRuleBasedHandover,
      lteHelper,
      ueLteDevs.Get(0),
      enbLteDevs,
      MilliSeconds(200)
   );

std::cout << "Live RSRP rule controller enabled\n";
    // TEMPORARY MANUAL CONTROLLER
   // Used to verify handover execution, NOT Random Forest inference.

//   Time firstHandoverTime = Seconds(120.0 / speedMs);
  // Time secondHandoverTime = Seconds(320.0 / speedMs);

  // lteHelper->HandoverRequest(
   //  firstHandoverTime,
   //  ueLteDevs.Get(0),
   //  enbLteDevs.Get(0),
    // enbLteDevs.Get(1)
 // );

   //lteHelper->HandoverRequest(
     //secondHandoverTime,
     //ueLteDevs.Get(0),
    // enbLteDevs.Get(1),
    // enbLteDevs.Get(2)
  // );

    std::cout << "MOBI-HO Lab - Live RSRP Handover Controller\n";
    // Handover decisions are now made automatically by A3-RSRP.

    // Uncomment to enable PCAP tracing
    // p2ph.EnablePcapAll("lena-x2-handover");

    lteHelper->EnablePhyTraces();
    lteHelper->EnableMacTraces();
    lteHelper->EnableRlcTraces();
    lteHelper->EnablePdcpTraces();
    Ptr<RadioBearerStatsCalculator> rlcStats = lteHelper->GetRlcStats();
    rlcStats->SetAttribute("EpochDuration", TimeValue(Seconds(0.05)));
    Ptr<RadioBearerStatsCalculator> pdcpStats = lteHelper->GetPdcpStats();
    pdcpStats->SetAttribute("EpochDuration", TimeValue(Seconds(0.05)));

    // connect custom trace sinks for RRC connection establishment and handover notification
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/ConnectionEstablished",
                    MakeCallback(&NotifyConnectionEstablishedEnb));
    Config::Connect("/NodeList/*/DeviceList/*/LteUeRrc/ConnectionEstablished",
                    MakeCallback(&NotifyConnectionEstablishedUe));
    Config::Connect(
    "/NodeList/*/DeviceList/*/LteUeRrc/RadioLinkFailure",
    MakeCallback(&NotifyRadioLinkFailure));

    Config::Connect(
      "/NodeList/*/DeviceList/*/LteUeRrc/ConnectionTimeout",
      MakeCallback(&NotifyConnectionTimeout));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverStart",
                    MakeCallback(&NotifyHandoverStartEnb));
    Config::Connect("/NodeList/*/DeviceList/*/LteUeRrc/HandoverStart",
                    MakeCallback(&NotifyHandoverStartUe));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverEndOk",
                    MakeCallback(&NotifyHandoverEndOkEnb));
    Config::Connect("/NodeList/*/DeviceList/*/LteUeRrc/HandoverEndOk",
                    MakeCallback(&NotifyHandoverEndOkUe));

    // Hook a trace sink (the same one) to the four handover failure traces
    
    Config::Connect(
          "/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureNoPreamble",
         MakeBoundCallback(
             &NotifyHandoverFailure,
             std::string("NO_PREAMBLE")
     )
   );

    Config::Connect(
         "/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureMaxRach",
      MakeBoundCallback(
         &NotifyHandoverFailure,
         std::string("MAX_RACH")
     )
  );

    Config::Connect(
         "/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureLeaving",
       MakeBoundCallback(
         &NotifyHandoverFailure,
         std::string("LEAVING")
    )
);

     Config::Connect(
       "/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureJoining",
      MakeBoundCallback(
        &NotifyHandoverFailure,
        std::string("JOINING")
    )
);


    Simulator::Stop(simTime + MilliSeconds(20));

    Config::Connect(
        "/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/"
        "LteUePhy/ReportUeMeasurements",
        MakeCallback(&NotifyRadioMeasurement));

    Simulator::Run();

    std::ofstream normalizedRadioCsv("radio.csv");

    NS_ABORT_MSG_IF(
           !normalizedRadioCsv.is_open(),
           "Cannot open radio.csv"
       );
     normalizedRadioCsv
        << "time_s,imsi,serving_cell_id,measured_cell_id,"
             "rsrp_dbm,rsrq_db,is_serving_cell\n";
    // Group measurments by UE and exact simulation  timestamp
    std::map<
         std::pair<uint64_t, double>,
         std::vector<RadioRecord>
    > snapshots;
    for (const auto& record : radioRecords)
    {
       snapshots[{record.imsi, record.time}].push_back(record);
     }
      
      uint32_t rejectedSnapshots = 0;
      uint32_t exportedRows = 0;
      
      for (const auto& snapshot : snapshots)
      {
          const auto& rows = snapshot.second;
          
          uint16_t servingCellId = 0;
          uint32_t servingCount =0;
      
          for (const auto& row : rows)
          {
             if(row.isServingCell)
              {
                servingCellId = row.measuredCellId;
                ++servingCount;
               }
           }
     
          //  Do not invent serving-cell indentities.
          if (servingCount != 1 || rows.size() < 2)
           {
               ++rejectedSnapshots;
               continue;
            } 
             for (const auto& row : rows)
             {
                normalizedRadioCsv
                    << std::fixed << std::setprecision(6)
                    << row.time << ","
                    << row.imsi << ","
                    << servingCellId << ","
                    << row.measuredCellId << ","
                    << row.rsrp << ","
                    << row.rsrq << ","
                    << (row.isServingCell ? 1 : 0)
                    << "\n";

                ++exportedRows;
   }
}
     normalizedRadioCsv.close();
   
     std::cout
        << "Radio rows exported: " << exportedRows
        << ",rejected snapshots: " << rejectedSnapshots 
        << std::endl;
    // GtkConfigStore config;
    // config.ConfigureAttributes ();

    Simulator::Destroy();
    radioCsv.close();
    handoverCsv.close();
    canonicalHandoverCsv.close();
    mobilityCsv.close();
    trafficCsv.close();
    packetsCsv.close();
    flowMetadataCsv.close();
    return 0;
}
