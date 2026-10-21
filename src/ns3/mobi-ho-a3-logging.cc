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
#include <fstream>
#include <iomanip>
// #include "ns3/gtk-config-store.h"
static std::ofstream handoverCsv;

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

NS_LOG_COMPONENT_DEFINE("LenaX2HandoverExample");

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
NotifyHandoverFailure(std::string context, uint64_t imsi, uint16_t cellid, uint16_t rnti)
{
    std::cout << Simulator::Now().As(Time::S) << " " << context << " eNB CellId " << cellid
              << " IMSI " << imsi << " RNTI " << rnti << " handover failure" << std::endl;
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

    // change some default attributes so that they are reasonable for
    // this scenario, but do this before processing command line
    // arguments, so that the user is allowed to override these settings
    Config::SetDefault("ns3::UdpClient::Interval", TimeValue(MilliSeconds(10)));
    Config::SetDefault("ns3::UdpClient::MaxPackets", UintegerValue(1000000));
    Config::SetDefault("ns3::LteHelper::UseIdealRrc", BooleanValue(false));

    // Command line arguments
    CommandLine cmd(__FILE__);
    cmd.AddValue("numberOfUes", "Number of UEs", numberOfUes);
    cmd.AddValue("numberOfEnbs", "Number of eNodeBs", numberOfEnbs);
    cmd.AddValue("speedKmh", "UE speed in km/h", speedKmh);
    cmd.AddValue("disableDl", "Disable downlink data flows", disableDl);
    cmd.AddValue("disableUl", "Disable uplink data flows", disableUl);
    cmd.Parse(argc, argv);
    handoverCsv.open("handover_events.csv",std::ios::out | std::ios::trunc);
    NS_ABORT_MSG_IF(!handoverCsv.is_open(),
    "Could not open handover_events.csv");
    handoverCsv
    << "time_s,imsi,cell_id,event,target_cell_id\n";

    NS_ABORT_MSG_IF(speedKmh <= 0.0, "Speed must be positive");
    simTime = Seconds(450.0 / (speedKmh / 3.6) + 2.0);

    Ptr<LteHelper> lteHelper = CreateObject<LteHelper>();
    Ptr<PointToPointEpcHelper> epcHelper = CreateObject<PointToPointEpcHelper>();
    lteHelper->SetEpcHelper(epcHelper);
    lteHelper->SetSchedulerType("ns3::RrFfMacScheduler");
    lteHelper->SetHandoverAlgorithmType(
        "ns3::A3RsrpHandoverAlgorithm");
    lteHelper->SetHandoverAlgorithmAttribute(
        "Hysteresis", DoubleValue(3.0));
    lteHelper->SetHandoverAlgorithmAttribute(
        "TimeToTrigger", TimeValue(MilliSeconds(256)));

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

    std::cout << "MOBI-HO Lab A3-RSRP Baseline\\n";
    std::cout << "Cells: " << numberOfEnbs << "\\n";
    std::cout << "UE speed: " << speedKmh << " km/h\\n";
    std::cout << "Simulation duration: "
              << simTime.GetSeconds() << " s\\n";

    // Install LTE Devices in eNB and UEs
    NetDeviceContainer enbLteDevs = lteHelper->InstallEnbDevice(enbNodes);
    NetDeviceContainer ueLteDevs = lteHelper->InstallUeDevice(ueNodes);

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
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverStart",
                    MakeCallback(&NotifyHandoverStartEnb));
    Config::Connect("/NodeList/*/DeviceList/*/LteUeRrc/HandoverStart",
                    MakeCallback(&NotifyHandoverStartUe));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverEndOk",
                    MakeCallback(&NotifyHandoverEndOkEnb));
    Config::Connect("/NodeList/*/DeviceList/*/LteUeRrc/HandoverEndOk",
                    MakeCallback(&NotifyHandoverEndOkUe));

    // Hook a trace sink (the same one) to the four handover failure traces
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureNoPreamble",
                    MakeCallback(&NotifyHandoverFailure));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureMaxRach",
                    MakeCallback(&NotifyHandoverFailure));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureLeaving",
                    MakeCallback(&NotifyHandoverFailure));
    Config::Connect("/NodeList/*/DeviceList/*/LteEnbRrc/HandoverFailureJoining",
                    MakeCallback(&NotifyHandoverFailure));

    Simulator::Stop(simTime + MilliSeconds(20));
    Simulator::Run();

    // GtkConfigStore config;
    // config.ConfigureAttributes ();

    Simulator::Destroy();
    handoverCsv.close();
    return 0;
}
